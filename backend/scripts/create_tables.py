#!/usr/bin/env python
"""Create DynamoDB tables for Stock Track Record."""
import sys
sys.path.insert(0, ".")
from app.db.dynamodb import get_dynamodb_resource, create_tables
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    print(f"Creating tables with prefix '{settings.dynamodb_table_prefix}' at {settings.dynamodb_endpoint}")
    resource = get_dynamodb_resource()
    create_tables(resource, prefix=settings.dynamodb_table_prefix)
    print("Tables created successfully.")
