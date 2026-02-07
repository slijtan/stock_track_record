# Spec 0002: Update AWS Deployment for DynamoDB

## Status: Draft
## Depends on: 0001 (MySQL to DynamoDB Local) — implemented

## Problem

Project 0001 migrated the application code from SQLAlchemy/MySQL to boto3/DynamoDB. However, the AWS deployment scripts (`deploy.sh`, `deploy_lambda.sh`) and Lambda configuration still reference:

- MySQL/Aurora database URL and connection strings
- SQLAlchemy, PyMySQL, and Alembic dependencies
- VPC configuration (needed only for RDS access)
- Old environment variables (`DATABASE_URL`)

The deployed Lambda functions will fail because the code now imports from `app.db.dynamodb` instead of `app.db.database`.

## Goals

1. Update deployment scripts to remove MySQL dependencies and add DynamoDB config
2. Update Lambda environment variables to use DynamoDB settings
3. Remove VPC configuration (DynamoDB is accessible without VPC)
4. Ensure Lambda IAM role has DynamoDB permissions
5. Create the DynamoDB tables in AWS (one-time setup)
6. Handle table creation for Lambda (tables must pre-exist, not created per-request)

## Non-Goals

- Migrating existing data from Aurora to DynamoDB (no production data to migrate)
- CloudFormation/IaC (keeping the existing manual deployment approach)
- Decommissioning Aurora resources (user can do this manually later)

## Technical Changes

### 1. deploy.sh

**Remove:**
- `sqlalchemy pymysql alembic` from pip install lines
- `DATABASE_URL=mysql+pymysql://...` from Lambda environment variables
- `--vpc-config SubnetIds=...,SecurityGroupIds=...` from both Lambda create commands
- `DB_ENDPOINT`, `VPC_SECURITY_GROUP`, `VPC_SUBNETS` variables

**Add/Update:**
- Environment variables: `DYNAMODB_TABLE_PREFIX=StockTrackRecord`, `DYNAMODB_REGION=us-east-1`
- Remove `DYNAMODB_ENDPOINT` (omitting it causes boto3 to use real AWS DynamoDB)

**Environment variable changes for API Lambda:**
```
Before: DATABASE_URL=mysql+pymysql://...,IS_LAMBDA=true,SQS_QUEUE_URL=...,FRONTEND_URL=...
After:  DYNAMODB_TABLE_PREFIX=StockTrackRecord,DYNAMODB_REGION=us-east-1,IS_LAMBDA=true,SQS_QUEUE_URL=...,FRONTEND_URL=...
```

**Environment variable changes for Worker Lambda:**
```
Before: DATABASE_URL=mysql+pymysql://...,IS_LAMBDA=true
After:  DYNAMODB_TABLE_PREFIX=StockTrackRecord,DYNAMODB_REGION=us-east-1,IS_LAMBDA=true
```

### 2. deploy_lambda.sh

**Remove:**
- No SQLAlchemy deps needed (they were in requirements-lambda.txt which was already updated in 0001)

**Fix:**
- Update hardcoded path from `/Users/ltan/Code/claude/stock_track_record/backend` to use `$(dirname "$0")` or similar

### 3. lambda_handler.py

The Mangum adapter uses `lifespan="off"`, so the `ensure_tables_exist()` call in `main.py`'s lifespan handler won't run in Lambda. This is correct — DynamoDB tables should be created once (via a setup script), not on every Lambda cold start.

No changes needed to `lambda_handler.py`.

### 4. IAM Permissions

The Lambda execution role (`stock-track-record-lambda-role`) needs DynamoDB permissions. Required policy:

```json
{
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
                "arn:aws:dynamodb:us-east-1:254713121560:table/StockTrackRecord",
                "arn:aws:dynamodb:us-east-1:254713121560:table/StockTrackRecord/index/*",
                "arn:aws:dynamodb:us-east-1:254713121560:table/StockTrackRecord-Stocks"
            ]
        }
    ]
}
```

### 5. Table Creation Script

A one-time script to create the DynamoDB tables in AWS:

```bash
# scripts/create_aws_tables.py
# Run locally with AWS credentials configured
DYNAMODB_ENDPOINT="" DYNAMODB_TABLE_PREFIX=StockTrackRecord python scripts/create_tables.py
```

The existing `scripts/create_tables.py` already works — just need to run it without `DYNAMODB_ENDPOINT` so boto3 connects to real AWS.

### 6. VPC Removal

With DynamoDB (public AWS endpoint), the Lambda functions no longer need VPC access. Removing VPC config improves cold start times significantly (VPC-attached Lambdas have slower cold starts).

**Note:** If the Lambda is currently attached to a VPC, updating the function with `--vpc-config SubnetIds='',SecurityGroupIds=''` will remove VPC access. This must be done carefully — the function code update and VPC removal should happen together.

## Files Changed

| File | Change |
|------|--------|
| `backend/deploy.sh` | Remove MySQL deps, VPC config, DATABASE_URL; add DynamoDB env vars |
| `backend/deploy_lambda.sh` | Fix hardcoded path |
| `backend/scripts/create_aws_tables.py` | New script for one-time AWS table creation |

## Testing

1. Run `create_aws_tables.py` to verify tables are created in AWS
2. Deploy using updated `deploy.sh`
3. Verify API Lambda responds to health check
4. Verify channel creation/listing works via the deployed API
5. Verify worker Lambda processes SQS messages

## Risks

- **IAM permissions**: If the Lambda role doesn't have DynamoDB access, all API calls will fail with AccessDeniedException
- **VPC removal timing**: Must remove VPC config simultaneously with the code update, not before
- **Table creation**: Tables must exist before first Lambda invocation
