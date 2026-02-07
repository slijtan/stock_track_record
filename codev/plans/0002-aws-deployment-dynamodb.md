# Plan 0002: Update AWS Deployment for DynamoDB

## Spec Reference
`codev/specs/0002-aws-deployment-dynamodb.md`

## Overview
Update Lambda deployment scripts to remove MySQL/Aurora references and add DynamoDB configuration. Small scope — primarily script edits, no application code changes.

## Implementation Steps

### Step 1: Update `deploy.sh`

**Remove:**
- `DB_ENDPOINT`, `VPC_SECURITY_GROUP`, `VPC_SUBNETS` variables (lines 11-13)
- `sqlalchemy pymysql alembic` from pip install line (line 39)
- `DATABASE_URL=mysql+pymysql://...` from both Lambda environment configs
- `--vpc-config` flags from both Lambda create commands

**Add:**
- DynamoDB environment variables to both Lambda functions:
  - `DYNAMODB_TABLE_PREFIX=StockTrackRecord`
  - `DYNAMODB_REGION=us-east-1`
  - `DYNAMODB_ENDPOINT=` (empty string → boto3 uses real AWS)

**Update environment variable blocks:**
- API Lambda: `DYNAMODB_TABLE_PREFIX=StockTrackRecord,DYNAMODB_REGION=us-east-1,DYNAMODB_ENDPOINT=,IS_LAMBDA=true,SQS_QUEUE_URL=${SQS_QUEUE_URL},FRONTEND_URL=https://d20r1f7t2ii5iy.cloudfront.net`
- Worker Lambda: `DYNAMODB_TABLE_PREFIX=StockTrackRecord,DYNAMODB_REGION=us-east-1,DYNAMODB_ENDPOINT=,IS_LAMBDA=true`

### Step 2: Update `deploy_lambda.sh`

- Fix hardcoded path `/Users/ltan/Code/claude/stock_track_record/backend` → use `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` and `cd "$SCRIPT_DIR"`

### Step 3: Create `scripts/create_aws_tables.sh`

Simple wrapper script that runs `create_tables.py` against real AWS DynamoDB:
```bash
#!/bin/bash
# Run from backend/ directory
DYNAMODB_ENDPOINT="" DYNAMODB_TABLE_PREFIX=StockTrackRecord python scripts/create_tables.py
```

### Step 4: Create `scripts/setup_iam_policy.sh`

Script to create and attach the DynamoDB IAM policy to the Lambda role:
- Create policy JSON with GetItem, PutItem, UpdateItem, DeleteItem, Query, Scan, BatchWriteItem permissions
- Scope to `arn:aws:dynamodb:us-east-1:254713121560:table/StockTrackRecord*`
- Attach to `stock-track-record-lambda-role`

### Step 5: Update `deploy.sh` — also add Lambda configuration update

For existing functions, add `update-function-configuration` calls to update environment variables and remove VPC:
- `aws lambda update-function-configuration` with new env vars
- `--vpc-config SubnetIds='',SecurityGroupIds=''` to detach VPC

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `backend/deploy.sh` | Modify | Remove MySQL deps/VPC/DB_URL, add DynamoDB env vars |
| `backend/deploy_lambda.sh` | Modify | Fix hardcoded path |
| `backend/scripts/create_aws_tables.sh` | Create | One-time AWS table creation wrapper |
| `backend/scripts/setup_iam_policy.sh` | Create | IAM policy setup for DynamoDB access |

## Testing

1. Verify scripts are syntactically valid (`bash -n deploy.sh`)
2. Review IAM policy covers all required DynamoDB actions
3. Dry-run review of environment variable changes

## Acceptance Criteria

1. `deploy.sh` has no MySQL/Aurora/VPC references
2. `deploy_lambda.sh` uses relative path
3. DynamoDB env vars configured for both Lambda functions
4. IAM policy script ready to run
5. Table creation script ready to run
