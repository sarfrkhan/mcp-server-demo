#!/bin/bash

# AWS CLI Deployment Script for MCP Lambda Servers
# Alternative to AWS SAM CLI

set -e

echo "🚀 Deploying MCP Servers to AWS Lambda using AWS CLI"

# Configuration
REGION=${AWS_REGION:-us-east-1}
S3_FUNCTION_NAME="s3-mcp-server"
KENDRA_FUNCTION_NAME="kendra-mcp-server"
API_KEY=${MCP_API_KEY:-""}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    echo_info "Checking prerequisites..."
    
    if ! command -v aws &> /dev/null; then
        echo_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        echo_error "Python 3 is not installed. Please install it first."
        exit 1
    fi
    
    if ! command -v zip &> /dev/null; then
        echo_error "zip command is not available. Please install it first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi
    
    echo_info "Prerequisites check passed!"
}

# Create IAM role for Lambda
create_iam_role() {
    local role_name=$1
    local policy_document=$2
    
    echo_info "Creating IAM role: $role_name"
    
    # Trust policy for Lambda
    cat > trust-policy.json << EOF
{
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
}
EOF

    # Create role if it doesn't exist
    if ! aws iam get-role --role-name $role_name &> /dev/null; then
        aws iam create-role \
            --role-name $role_name \
            --assume-role-policy-document file://trust-policy.json
        
        # Attach basic Lambda execution policy
        aws iam attach-role-policy \
            --role-name $role_name \
            --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
        
        # Attach custom policy
        aws iam put-role-policy \
            --role-name $role_name \
            --policy-name ${role_name}-policy \
            --policy-document "$policy_document"
        
        echo_info "Waiting for role to be available..."
        sleep 10
    else
        echo_info "Role $role_name already exists"
    fi
    
    rm -f trust-policy.json
}

# Package Lambda function
package_lambda() {
    local function_dir=$1
    local zip_file=$2
    
    echo_info "Packaging Lambda function from $function_dir"
    
    cd $function_dir
    
    # Create virtual environment and install dependencies
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt -t .
    
    # Copy shared utilities
    cp -r ../shared/* .
    
    # Create zip package
    zip -r ../$zip_file . -x "venv/*" "*.pyc" "__pycache__/*"
    
    deactivate
    rm -rf venv
    cd ..
    
    echo_info "Package created: $zip_file"
}

# Deploy Lambda function
deploy_lambda() {
    local function_name=$1
    local zip_file=$2
    local role_arn=$3
    local env_vars=$4
    
    echo_info "Deploying Lambda function: $function_name"
    
    # Check if function exists
    if aws lambda get-function --function-name $function_name &> /dev/null; then
        echo_info "Updating existing function..."
        aws lambda update-function-code \
            --function-name $function_name \
            --zip-file fileb://$zip_file
        
        aws lambda update-function-configuration \
            --function-name $function_name \
            --environment "Variables={$env_vars}"
    else
        echo_info "Creating new function..."
        aws lambda create-function \
            --function-name $function_name \
            --runtime python3.11 \
            --role $role_arn \
            --handler lambda_function.lambda_handler \
            --zip-file fileb://$zip_file \
            --timeout 30 \
            --memory-size 512 \
            --environment "Variables={$env_vars}"
    fi
}

# Create API Gateway
create_api_gateway() {
    local api_name=$1
    local function_name=$2
    
    echo_info "Creating API Gateway for $function_name"
    
    # Create REST API
    API_ID=$(aws apigateway create-rest-api \
        --name $api_name \
        --query 'id' \
        --output text)
    
    echo_info "Created API: $API_ID"
    
    # Get root resource ID
    ROOT_RESOURCE_ID=$(aws apigateway get-resources \
        --rest-api-id $API_ID \
        --query 'items[0].id' \
        --output text)
    
    # Create proxy resource
    PROXY_RESOURCE_ID=$(aws apigateway create-resource \
        --rest-api-id $API_ID \
        --parent-id $ROOT_RESOURCE_ID \
        --path-part '{proxy+}' \
        --query 'id' \
        --output text)
    
    # Create ANY method
    aws apigateway put-method \
        --rest-api-id $API_ID \
        --resource-id $PROXY_RESOURCE_ID \
        --http-method ANY \
        --authorization-type NONE
    
    # Get Lambda function ARN
    FUNCTION_ARN=$(aws lambda get-function \
        --function-name $function_name \
        --query 'Configuration.FunctionArn' \
        --output text)
    
    # Set up integration
    aws apigateway put-integration \
        --rest-api-id $API_ID \
        --resource-id $PROXY_RESOURCE_ID \
        --http-method ANY \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$FUNCTION_ARN/invocations"
    
    # Add Lambda permission for API Gateway
    aws lambda add-permission \
        --function-name $function_name \
        --statement-id apigateway-invoke \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:apigateway:$REGION:*" || true
    
    # Deploy API
    aws apigateway create-deployment \
        --rest-api-id $API_ID \
        --stage-name prod
    
    # Return API URL
    echo "https://$API_ID.execute-api.$REGION.amazonaws.com/prod"
}

# Main deployment function
main() {
    echo_info "Starting deployment process..."
    
    check_prerequisites
    
    # S3 Lambda deployment
    echo_info "=== Deploying S3 MCP Server ==="
    
    # Create S3 IAM role
    S3_POLICY='{
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
    }'
    
    create_iam_role "s3-mcp-lambda-role" "$S3_POLICY"
    S3_ROLE_ARN=$(aws iam get-role --role-name s3-mcp-lambda-role --query 'Role.Arn' --output text)
    
    # Package and deploy S3 function
    package_lambda "s3-lambda" "s3-lambda.zip"
    deploy_lambda "$S3_FUNCTION_NAME" "s3-lambda.zip" "$S3_ROLE_ARN" "MCP_API_KEY=$API_KEY"
    
    # Create S3 API Gateway
    S3_API_URL=$(create_api_gateway "s3-mcp-api" "$S3_FUNCTION_NAME")
    
    # Kendra Lambda deployment
    echo_info "=== Deploying Kendra MCP Server ==="
    
    # Create Kendra IAM role
    KENDRA_POLICY='{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "kendra:Query",
                    "kendra:ListIndices",
                    "kendra:DescribeIndex"
                ],
                "Resource": "*"
            }
        ]
    }'
    
    create_iam_role "kendra-mcp-lambda-role" "$KENDRA_POLICY"
    KENDRA_ROLE_ARN=$(aws iam get-role --role-name kendra-mcp-lambda-role --query 'Role.Arn' --output text)
    
    # Package and deploy Kendra function
    package_lambda "kendra-lambda" "kendra-lambda.zip"
    deploy_lambda "$KENDRA_FUNCTION_NAME" "kendra-lambda.zip" "$KENDRA_ROLE_ARN" "MCP_API_KEY=$API_KEY,KENDRA_INDEX_ID=${KENDRA_INDEX_ID:-}"
    
    # Create Kendra API Gateway
    KENDRA_API_URL=$(create_api_gateway "kendra-mcp-api" "$KENDRA_FUNCTION_NAME")
    
    # Cleanup
    rm -f s3-lambda.zip kendra-lambda.zip
    
    # Output results
    echo_info "=== Deployment Complete! ==="
    echo ""
    echo "🎉 Your MCP servers are now deployed!"
    echo ""
    echo "S3 API URL: $S3_API_URL"
    echo "Kendra API URL: $KENDRA_API_URL"
    echo ""
    echo "Update your Cline configuration:"
    echo '{'
    echo '  "mcpServers": {'
    echo "    \"s3-aws\": {"
    echo "      \"command\": \"npx\","
    echo "      \"args\": [\"mcp-remote\", \"$S3_API_URL\"]"
    echo "    },"
    echo "    \"kendra-aws\": {"
    echo "      \"command\": \"npx\","
    echo "      \"args\": [\"mcp-remote\", \"$KENDRA_API_URL\"]"
    echo "    }"
    echo '  }'
    echo '}'
}

# Run main function
main "$@"
