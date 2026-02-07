import time

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

from app.config import get_settings

_resource = None
_client = None


def get_dynamodb_resource():
    """Shared boto3 DynamoDB resource (singleton, thread-safe for operations)."""
    global _resource
    if _resource is None:
        settings = get_settings()
        kwargs = {"region_name": settings.dynamodb_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
            kwargs["aws_access_key_id"] = "local"
            kwargs["aws_secret_access_key"] = "local"
        _resource = boto3.resource("dynamodb", **kwargs)
    return _resource


def get_dynamodb_client():
    """Shared boto3 DynamoDB client (singleton, thread-safe for operations)."""
    global _client
    if _client is None:
        settings = get_settings()
        kwargs = {"region_name": settings.dynamodb_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
            kwargs["aws_access_key_id"] = "local"
            kwargs["aws_secret_access_key"] = "local"
        _client = boto3.client("dynamodb", **kwargs)
    return _client


def get_table(suffix: str = ""):
    """Get a DynamoDB Table object. '' = main table, '-Stocks' = stocks table."""
    settings = get_settings()
    resource = get_dynamodb_resource()
    return resource.Table(settings.dynamodb_table_prefix + suffix)


def reset_clients():
    """Reset cached clients (for testing)."""
    global _resource, _client
    _resource = None
    _client = None


def query_all_pages(table, **kwargs) -> list:
    """Query DynamoDB following all LastEvaluatedKey pages. Handles 1MB limit."""
    items = []
    response = table.query(**kwargs)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
    return items


def query_count(table, **kwargs) -> int:
    """Query DynamoDB with Select=COUNT, following all pages."""
    kwargs["Select"] = "COUNT"
    total = 0
    response = table.query(**kwargs)
    total += response.get("Count", 0)
    while "LastEvaluatedKey" in response:
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.query(**kwargs)
        total += response.get("Count", 0)
    return total


def batch_delete_items(table, items: list):
    """Delete items using batch_writer (handles batching + retries automatically)."""
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})


def create_tables(resource=None, prefix=None):
    """Create all DynamoDB tables."""
    if resource is None:
        resource = get_dynamodb_resource()
    if prefix is None:
        prefix = get_settings().dynamodb_table_prefix

    # Main table with 3 GSIs
    resource.create_table(
        TableName=prefix,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
            {"AttributeName": "GSI2PK", "AttributeType": "S"},
            {"AttributeName": "GSI3PK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1-index",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "GSI2-index",
                "KeySchema": [
                    {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "GSI3-index",
                "KeySchema": [
                    {"AttributeName": "GSI3PK", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "KEYS_ONLY"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Stocks table
    resource.create_table(
        TableName=f"{prefix}-Stocks",
        KeySchema=[
            {"AttributeName": "ticker", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "ticker", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def delete_tables(resource=None, prefix=None):
    """Delete all DynamoDB tables."""
    if resource is None:
        resource = get_dynamodb_resource()
    if prefix is None:
        prefix = get_settings().dynamodb_table_prefix

    for suffix in ["", "-Stocks"]:
        try:
            table = resource.Table(f"{prefix}{suffix}")
            table.delete()
            table.wait_until_not_exists()
        except ClientError:
            pass


def _create_table_if_not_exists(resource, **kwargs):
    """Create a single table, ignoring if it already exists."""
    try:
        resource.create_table(**kwargs)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            pass  # Table already exists
        else:
            raise


def ensure_tables_exist():
    """Create tables if they don't exist (idempotent). Called on app startup."""
    resource = get_dynamodb_resource()
    prefix = get_settings().dynamodb_table_prefix

    # Main table
    _create_table_if_not_exists(
        resource,
        TableName=prefix,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
            {"AttributeName": "GSI2PK", "AttributeType": "S"},
            {"AttributeName": "GSI3PK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1-index",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "GSI2-index",
                "KeySchema": [
                    {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "GSI3-index",
                "KeySchema": [
                    {"AttributeName": "GSI3PK", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "KEYS_ONLY"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Stocks table
    _create_table_if_not_exists(
        resource,
        TableName=f"{prefix}-Stocks",
        KeySchema=[
            {"AttributeName": "ticker", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "ticker", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
