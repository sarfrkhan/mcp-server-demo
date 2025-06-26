#!/bin/bash

# Master deployment script for all MCP Lambda servers

echo "Deploying all MCP Lambda servers to AWS..."

# Configuration
REGION="us-east-1"  # Change this to your preferred region

echo "Using AWS region: $REGION"
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "Error: AWS CLI is not configured or credentials are invalid."
    echo "Please run 'aws configure' to set up your credentials."
    exit 1
fi

# Get account info
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Deploying to AWS Account: $ACCOUNT_ID"
echo ""

# Deploy S3 MCP Server
echo "=== Deploying S3 MCP Server ==="
cd ../s3-lambda
chmod +x deploy.sh
./deploy.sh
if [ $? -eq 0 ]; then
    echo "✅ S3 MCP Server deployed successfully"
else
    echo "❌ S3 MCP Server deployment failed"
fi
echo ""

# Deploy Kendra MCP Server
echo "=== Deploying Kendra MCP Server ==="
cd ../kendra-lambda
chmod +x deploy.sh
./deploy.sh
if [ $? -eq 0 ]; then
    echo "✅ Kendra MCP Server deployed successfully"
else
    echo "❌ Kendra MCP Server deployment failed"
fi
echo ""

# Return to infrastructure directory
cd ../infrastructure

echo "=== Deployment Summary ==="
echo "All MCP servers have been deployed to AWS Lambda + API Gateway"
echo ""
echo "Your MCP server endpoints:"
echo "- S3 Server: Check output from S3 deployment above"
echo "- Kendra Server: Check output from Kendra deployment above"
echo ""
echo "To use these servers in Cline, add the endpoints to your MCP configuration."
echo "Example configuration will be shown in each deployment output above."
echo ""
echo "Next steps:"
echo "1. Test the API endpoints to ensure they're working"
echo "2. Configure your Cline MCP settings with the new endpoints"
echo "3. For Kendra server, set KENDRA_INDEX_ID environment variable if needed"
echo ""
echo "Deployment completed! 🎉"
