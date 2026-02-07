#!/bin/bash
# Attach DynamoDB permissions to the Lambda execution role (one-time setup).
#
# Prerequisites:
#   - AWS CLI configured with IAM permissions (iam:PutRolePolicy)
#   - Run from anywhere
#
# Usage:
#   ./scripts/setup_iam_policy.sh

set -e

AWS_REGION="us-east-1"
ACCOUNT_ID="254713121560"
ROLE_NAME="stock-track-record-lambda-role"
POLICY_NAME="stock-track-record-dynamodb-access"

echo "Attaching DynamoDB policy to role: ${ROLE_NAME}"

aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "$POLICY_NAME" \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                    "dynamodb:BatchWriteItem"
                ],
                "Resource": [
                    "arn:aws:dynamodb:'"${AWS_REGION}"':'"${ACCOUNT_ID}"':table/StockTrackRecord",
                    "arn:aws:dynamodb:'"${AWS_REGION}"':'"${ACCOUNT_ID}"':table/StockTrackRecord/index/*",
                    "arn:aws:dynamodb:'"${AWS_REGION}"':'"${ACCOUNT_ID}"':table/StockTrackRecord-Stocks"
                ]
            }
        ]
    }'

echo "Policy '${POLICY_NAME}' attached to role '${ROLE_NAME}'."
echo ""
echo "Verify at: https://console.aws.amazon.com/iam/home#/roles/${ROLE_NAME}"
