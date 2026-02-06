#!/bin/bash
set -e

# Configuration
AWS_REGION="us-east-1"
ACCOUNT_ID="254713121560"
API_FUNCTION_NAME="stock-track-record-api"
WORKER_FUNCTION_NAME="stock-track-record-worker"
LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/stock-track-record-lambda-role"
SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/${ACCOUNT_ID}/stock-track-record-processing-queue"
DB_ENDPOINT="stock-track-record-cluster.cluster-c2hgmi4acygb.us-east-1.rds.amazonaws.com"
VPC_SECURITY_GROUP="sg-05967718937fd7fa4"
VPC_SUBNETS="subnet-3104673d,subnet-d6bd1ffd,subnet-39483a5c"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Building Lambda deployment package...${NC}"

# Create temp directory for package
rm -rf /tmp/lambda-package
mkdir -p /tmp/lambda-package

# Install dependencies into package directory (Linux x86_64 for Lambda)
# First, install packages with native extensions using Linux wheels
pip install pydantic pydantic-core aiohttp -t /tmp/lambda-package --quiet --upgrade \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all:

# Then install the rest of the requirements (pure Python packages)
pip install -r requirements.txt -t /tmp/lambda-package --quiet --upgrade --no-deps

# Install remaining dependencies
pip install annotated-types typing_extensions anyio starlette mangum httpx google-genai \
    sqlalchemy pymysql alembic pydantic-settings python-dotenv httpcore sniffio certifi idna h11 \
    google-api-python-client google-auth google-auth-httplib2 httplib2 uritemplate pyparsing \
    cachetools pyasn1 pyasn1-modules rsa youtube-transcript-api yfinance \
    -t /tmp/lambda-package --quiet --upgrade

# Copy application code
cp -r app /tmp/lambda-package/
cp lambda_handler.py /tmp/lambda-package/
cp worker_handler.py /tmp/lambda-package/

# Remove unnecessary files to reduce package size
find /tmp/lambda-package -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /tmp/lambda-package -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find /tmp/lambda-package -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
rm -rf /tmp/lambda-package/boto3 /tmp/lambda-package/botocore 2>/dev/null || true  # Already in Lambda runtime

# Create zip file
cd /tmp/lambda-package
zip -r9 /tmp/lambda-deployment.zip . -x "*.pyc" -x "*__pycache__*" > /dev/null

PACKAGE_SIZE=$(du -h /tmp/lambda-deployment.zip | cut -f1)
echo -e "${GREEN}Package created: /tmp/lambda-deployment.zip (${PACKAGE_SIZE})${NC}"

echo -e "${YELLOW}Deploying API Lambda...${NC}"

# Check if function exists
if aws lambda get-function --function-name $API_FUNCTION_NAME --region $AWS_REGION 2>/dev/null; then
    echo "Updating existing API Lambda function..."
    aws lambda update-function-code \
        --function-name $API_FUNCTION_NAME \
        --zip-file fileb:///tmp/lambda-deployment.zip \
        --region $AWS_REGION > /dev/null
else
    echo "Creating new API Lambda function..."
    aws lambda create-function \
        --function-name $API_FUNCTION_NAME \
        --runtime python3.11 \
        --handler lambda_handler.handler \
        --role $LAMBDA_ROLE_ARN \
        --zip-file fileb:///tmp/lambda-deployment.zip \
        --timeout 30 \
        --memory-size 512 \
        --environment "Variables={DATABASE_URL=mysql+pymysql://admin:StockTrack2024Secure@${DB_ENDPOINT}:3306/stock_track_record,IS_LAMBDA=true,SQS_QUEUE_URL=${SQS_QUEUE_URL},FRONTEND_URL=https://d20r1f7t2ii5iy.cloudfront.net}" \
        --vpc-config SubnetIds=${VPC_SUBNETS},SecurityGroupIds=${VPC_SECURITY_GROUP} \
        --region $AWS_REGION > /dev/null
fi

echo -e "${GREEN}API Lambda deployed!${NC}"

echo -e "${YELLOW}Deploying Worker Lambda...${NC}"

if aws lambda get-function --function-name $WORKER_FUNCTION_NAME --region $AWS_REGION 2>/dev/null; then
    echo "Updating existing Worker Lambda function..."
    aws lambda update-function-code \
        --function-name $WORKER_FUNCTION_NAME \
        --zip-file fileb:///tmp/lambda-deployment.zip \
        --region $AWS_REGION > /dev/null
else
    echo "Creating new Worker Lambda function..."
    aws lambda create-function \
        --function-name $WORKER_FUNCTION_NAME \
        --runtime python3.11 \
        --handler worker_handler.handler \
        --role $LAMBDA_ROLE_ARN \
        --zip-file fileb:///tmp/lambda-deployment.zip \
        --timeout 900 \
        --memory-size 1024 \
        --environment "Variables={DATABASE_URL=mysql+pymysql://admin:StockTrack2024Secure@${DB_ENDPOINT}:3306/stock_track_record,IS_LAMBDA=true}" \
        --vpc-config SubnetIds=${VPC_SUBNETS},SecurityGroupIds=${VPC_SECURITY_GROUP} \
        --region $AWS_REGION > /dev/null
fi

echo -e "${GREEN}Worker Lambda deployed!${NC}"

echo -e "${GREEN}Deployment complete!${NC}"
