#!/bin/bash
# Create DynamoDB tables in AWS (one-time setup).
#
# Prerequisites:
#   - AWS CLI configured with credentials that have DynamoDB:CreateTable permission
#   - Run from the backend/ directory
#
# Usage:
#   ./scripts/create_aws_tables.sh
#
# This runs the existing create_tables.py with DYNAMODB_ENDPOINT unset,
# so boto3 connects to real AWS DynamoDB instead of DynamoDB Local.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "Creating DynamoDB tables in AWS..."
echo "Region: us-east-1"
echo "Table prefix: StockTrackRecord"

DYNAMODB_ENDPOINT="" \
DYNAMODB_TABLE_PREFIX="StockTrackRecord" \
DYNAMODB_REGION="us-east-1" \
python scripts/create_tables.py

echo "Done. Verify tables in AWS Console: https://console.aws.amazon.com/dynamodbv2/home?region=us-east-1#tables"
