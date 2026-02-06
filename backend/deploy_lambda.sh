#!/bin/bash
set -e

cd /Users/ltan/Code/claude/stock_track_record/backend

echo "Cleaning up..."
rm -rf package

echo "Building with Docker (x86_64 for Lambda)..."
docker run --rm --platform linux/amd64 -v "$(pwd)":/var/task public.ecr.aws/sam/build-python3.11:latest bash -c "
    pip install --upgrade pip && \
    pip install -r /var/task/requirements-lambda.txt -t /var/task/package --only-binary=:all: && \

    # Remove boto3/botocore (already in Lambda runtime)
    rm -rf /var/task/package/boto3 /var/task/package/botocore && \

    # Keep numpy and pandas in package (no layer needed)

    # Remove testing packages if accidentally installed
    rm -rf /var/task/package/pytest* && \

    # Remove unnecessary files to reduce size
    find /var/task/package -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
    find /var/task/package -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true && \
    find /var/task/package -type d -name 'test' -exec rm -rf {} + 2>/dev/null || true && \
    find /var/task/package -type d -name '*.dist-info' -exec rm -rf {} + 2>/dev/null || true && \
    find /var/task/package -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true && \
    find /var/task/package -name '*.pyc' -delete 2>/dev/null || true && \
    find /var/task/package -name '*.pyo' -delete 2>/dev/null || true && \

    # Remove uvicorn (not needed for Lambda)
    rm -rf /var/task/package/uvicorn 2>/dev/null || true && \
    rm -rf /var/task/package/uvloop 2>/dev/null || true && \
    rm -rf /var/task/package/watchfiles 2>/dev/null || true && \

    # Print size after cleanup
    echo 'Package size after cleanup:' && \
    du -sh /var/task/package
"

echo "Copying app code..."
cp -r app lambda_handler.py worker_handler.py package/

echo "Creating zip..."
cd package && zip -r9 ../lambda-deployment.zip . -x "*.pyc" -x "*__pycache__*" > /dev/null

echo "Package size:"
ls -lh ../lambda-deployment.zip

echo "Uploading to S3..."
cd ..
aws s3 cp lambda-deployment.zip s3://stock-track-record-frontend-254713121560/

echo "Updating API Lambda..."
aws lambda update-function-code --function-name stock-track-record-api --s3-bucket stock-track-record-frontend-254713121560 --s3-key lambda-deployment.zip --region us-east-1 --query "LastUpdateStatus" --output text

echo "Waiting for API Lambda update..."
aws lambda wait function-updated --function-name stock-track-record-api --region us-east-1

echo "Updating Worker Lambda..."
aws lambda update-function-code --function-name stock-track-record-worker --s3-bucket stock-track-record-frontend-254713121560 --s3-key lambda-deployment.zip --region us-east-1 --query "LastUpdateStatus" --output text

echo "Cleaning up S3..."
aws s3 rm s3://stock-track-record-frontend-254713121560/lambda-deployment.zip

echo "Done!"
