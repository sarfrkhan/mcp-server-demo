#!/bin/bash

# S3 MCP Server Lambda Deployment Script

# Configuration
FUNCTION_NAME="s3-mcp-server"
REGION="us-east-1"  # Change this to your preferred region
ROLE_NAME="s3-mcp-lambda-role"
POLICY_NAME="s3-mcp-lambda-policy"

echo "Deploying S3 MCP Server to AWS Lambda..."

# Create deployment package
echo "Creating deployment package..."
rm -rf package
mkdir package

# Install dependencies
pip install -r requirements.txt -t package/

# Copy lambda function
cp lambda_function.py package/

# Create zip file using Python
python -c "
import zipfile
import os

def create_zip(source_dir, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)

create_zip('package', 's3-mcp-lambda.zip')
print('Created s3-mcp-lambda.zip successfully')
"

# Create IAM role if it doesn't exist
echo "Creating IAM role..."
aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }' \
    --region $REGION 2>/dev/null || echo "Role already exists"

# Attach basic Lambda execution policy
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --region $REGION

# Create and attach S3 access policy
aws iam put-role-policy \
    --role-name $ROLE_NAME \
    --policy-name $POLICY_NAME \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:*"
                ],
                "Resource": "*"
            }
        ]
    }' \
    --region $REGION

# Get account ID for role ARN
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"

# Wait for role to be ready
echo "Waiting for IAM role to be ready..."
sleep 10

# Create or update Lambda function
echo "Creating/updating Lambda function..."
aws lambda create-function \
    --function-name $FUNCTION_NAME \
    --runtime python3.9 \
    --role $ROLE_ARN \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://s3-mcp-lambda.zip \
    --timeout 30 \
    --memory-size 256 \
    --region $REGION 2>/dev/null || \
aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb://s3-mcp-lambda.zip \
    --region $REGION

# Create API Gateway
echo "Creating API Gateway..."
API_ID=$(aws apigateway create-rest-api \
    --name "s3-mcp-api" \
    --description "API Gateway for S3 MCP Server" \
    --region $REGION \
    --query 'id' \
    --output text 2>/dev/null || \
aws apigateway get-rest-apis \
    --query "items[?name=='s3-mcp-api'].id" \
    --output text \
    --region $REGION)

# Get root resource ID
ROOT_ID=$(aws apigateway get-resources \
    --rest-api-id $API_ID \
    --region $REGION \
    --query 'items[?path==`/`].id' \
    --output text)

# Create resource for MCP endpoint
RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id $API_ID \
    --parent-id $ROOT_ID \
    --path-part "s3-mcp" \
    --region $REGION \
    --query 'id' \
    --output text 2>/dev/null || \
aws apigateway get-resources \
    --rest-api-id $API_ID \
    --region $REGION \
    --query "items[?pathPart=='s3-mcp'].id" \
    --output text)

# Create GET method for SSE connection
aws apigateway put-method \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method GET \
    --authorization-type NONE \
    --region $REGION 2>/dev/null || echo "GET method already exists"

# Create POST method for MCP messages
aws apigateway put-method \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method POST \
    --authorization-type NONE \
    --region $REGION 2>/dev/null || echo "POST method already exists"

# Create OPTIONS method for CORS
aws apigateway put-method \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method OPTIONS \
    --authorization-type NONE \
    --region $REGION 2>/dev/null || echo "OPTIONS method already exists"

# Set up Lambda integration for GET (SSE connection)
aws apigateway put-integration \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method GET \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/arn:aws:lambda:$REGION:$ACCOUNT_ID:function:$FUNCTION_NAME/invocations" \
    --region $REGION 2>/dev/null || echo "GET integration already exists"

# Set up Lambda integration for POST (MCP messages)
aws apigateway put-integration \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/arn:aws:lambda:$REGION:$ACCOUNT_ID:function:$FUNCTION_NAME/invocations" \
    --region $REGION 2>/dev/null || echo "POST integration already exists"

# Set up OPTIONS integration for CORS
aws apigateway put-integration \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method OPTIONS \
    --type MOCK \
    --request-templates '{"application/json": "{\"statusCode\": 200}"}' \
    --region $REGION 2>/dev/null || echo "OPTIONS integration already exists"

# Set up method responses
aws apigateway put-method-response \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method GET \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Origin": false}' \
    --region $REGION 2>/dev/null || echo "GET method response already exists"

aws apigateway put-method-response \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method POST \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Origin": false}' \
    --region $REGION 2>/dev/null || echo "POST method response already exists"

aws apigateway put-method-response \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Origin": false, "method.response.header.Access-Control-Allow-Methods": false, "method.response.header.Access-Control-Allow-Headers": false}' \
    --region $REGION 2>/dev/null || echo "OPTIONS method response already exists"

# Set up integration responses
aws apigateway put-integration-response \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method GET \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Origin": "'"'"'*'"'"'"}' \
    --region $REGION 2>/dev/null || echo "GET integration response already exists"

aws apigateway put-integration-response \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method POST \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Origin": "'"'"'*'"'"'"}' \
    --region $REGION 2>/dev/null || echo "POST integration response already exists"

aws apigateway put-integration-response \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Origin": "'"'"'*'"'"'", "method.response.header.Access-Control-Allow-Methods": "'"'"'GET,POST,OPTIONS'"'"'", "method.response.header.Access-Control-Allow-Headers": "'"'"'Content-Type'"'"'"}' \
    --response-templates '{"application/json": ""}' \
    --region $REGION 2>/dev/null || echo "OPTIONS integration response already exists"

# Grant API Gateway permission to invoke Lambda
aws lambda add-permission \
    --function-name $FUNCTION_NAME \
    --statement-id apigateway-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*/*" \
    --region $REGION 2>/dev/null || echo "Permission already exists"

# Deploy API
echo "Deploying API..."
aws apigateway create-deployment \
    --rest-api-id $API_ID \
    --stage-name prod \
    --region $REGION

# Get API endpoint
API_ENDPOINT="https://$API_ID.execute-api.$REGION.amazonaws.com/prod/s3-mcp"

echo ""
echo "Deployment completed!"
echo "API Endpoint: $API_ENDPOINT"
echo ""
echo "To use this MCP server in Cline:"
echo ""
echo "Method 1: Using Cline's Remote Servers Interface (Recommended)"
echo "1. Open Cline → Menu (⋮) → 'MCP Servers'"
echo "2. Click 'Remote Servers' tab"
echo "3. Add server:"
echo "   - Server Name: S3 MCP Server"
echo "   - Server URL: $API_ENDPOINT"
echo "   - Click 'Add Server'"
echo ""
echo "Method 2: Manual Configuration File"
echo '{'
echo '  "mcpServers": {'
echo '    "s3-server": {'
echo '      "url": "'$API_ENDPOINT'",'
echo '      "disabled": false'
echo '    }'
echo '  }'
echo '}'
echo ""

# Cleanup
rm -rf package s3-mcp-lambda.zip
