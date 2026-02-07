import os
import uuid

import pytest
import boto3
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ.setdefault("DYNAMODB_ENDPOINT", "http://localhost:8000")
os.environ.setdefault("DYNAMODB_REGION", "us-east-1")


@pytest.fixture(scope="function")
def table_prefix():
    """Generate a unique table prefix for test isolation."""
    return f"Test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="function")
def dynamodb_tables(table_prefix, monkeypatch):
    """Create DynamoDB tables for testing with unique prefix, tear down after test."""
    from app.db import dynamodb as dynamodb_module

    # Override settings for this test
    monkeypatch.setenv("DYNAMODB_TABLE_PREFIX", table_prefix)

    # Reset cached clients and settings so they pick up new env
    dynamodb_module.reset_clients()

    # Clear the settings cache
    from app.config import get_settings
    get_settings.cache_clear()

    # Create tables
    resource = dynamodb_module.get_dynamodb_resource()
    dynamodb_module.create_tables(resource, prefix=table_prefix)

    yield table_prefix

    # Teardown: delete tables
    dynamodb_module.delete_tables(resource, prefix=table_prefix)
    dynamodb_module.reset_clients()
    get_settings.cache_clear()


@pytest.fixture(scope="function")
def client(dynamodb_tables):
    """Create a test client with DynamoDB tables."""
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def client_no_db():
    """Create a test client without database (for health check tests)."""
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
