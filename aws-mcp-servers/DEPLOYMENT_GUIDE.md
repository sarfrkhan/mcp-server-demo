# AWS Lambda MCP Servers Deployment Guide

This guide will help you deploy your S3 and Kendra MCP servers to AWS Lambda.

## Prerequisites

1. **AWS CLI** installed and configured with your credentials
2. **AWS SAM CLI** installed ([Installation Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))
3. **Python 3.11** installed
4. **Node.js** (for mcp-remote tool)

## Quick Setup Commands

```bash
# Install AWS SAM CLI (if not already installed)
# Follow: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

# Install mcp-remote tool
npm install -g mcp-remote
```

## Deployment Steps

### 1. Deploy S3 MCP Server

```bash
cd aws-mcp-servers/s3-lambda

# Build the Lambda function
sam build

# Deploy (first time - will prompt for configuration)
sam deploy --guided

# For subsequent deployments
sam deploy
```

**During guided deployment, you'll be asked:**
- Stack name: `s3-mcp-stack` (or your choice)
- AWS Region: Choose your preferred region
- ApiKeyParameter: Leave empty for no auth, or set a secure API key
- Confirm changes: Y
- Allow SAM to create IAM roles: Y
- Save parameters to config file: Y

### 2. Deploy Kendra MCP Server

```bash
cd ../kendra-lambda

# Build the Lambda function
sam build

# Deploy (first time - will prompt for configuration)
sam deploy --guided

# For subsequent deployments
sam deploy
```

**During guided deployment, you'll be asked:**
- Stack name: `kendra-mcp-stack` (or your choice)
- AWS Region: Same as S3 deployment
- ApiKeyParameter: Use same API key as S3 (or leave empty)
- KendraIndexId: Your Kendra index ID (optional)
- Confirm changes: Y
- Allow SAM to create IAM roles: Y
- Save parameters to config file: Y

## Getting Your API Endpoints

After deployment, SAM will output your API endpoints. They'll look like:

```
S3MCPApiUrl: https://abc123def.execute-api.us-east-1.amazonaws.com/prod/s3
KendraMCPApiUrl: https://xyz789ghi.execute-api.us-east-1.amazonaws.com/prod/kendra
```

## Testing Your Deployments

### Test S3 Server
```bash
# List buckets (no auth)
curl https://your-s3-api-url/listBuckets

# List buckets (with API key)
curl -H "X-API-Key: your-api-key" https://your-s3-api-url/listBuckets
```

### Test Kendra Server
```bash
# List indexes
curl https://your-kendra-api-url/listIndexes

# Query (replace with your index ID)
curl -X POST https://your-kendra-api-url/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test search", "indexId": "your-index-id"}'
```

## Configure Cline to Use AWS Lambda Servers

Update your Cline MCP configuration:

```json
{
  "mcpServers": {
    "s3-aws": {
      "command": "npx",
      "args": ["mcp-remote", "https://your-s3-api-url"]
    },
    "kendra-aws": {
      "command": "npx", 
      "args": ["mcp-remote", "https://your-kendra-api-url"]
    }
  }
}
```

## API Endpoints Reference

### S3 Server Endpoints
- `GET /s3/listBuckets` - List all buckets
- `POST /s3/createBucket` - Create bucket
- `DELETE /s3/deleteBucket` - Delete bucket
- `GET /s3/listObjects?BucketName=bucket` - List objects
- `GET /s3/getObject?BucketName=bucket&Key=key` - Get object
- `POST /s3/putObject` - Upload object
- `DELETE /s3/deleteObject` - Delete object

### Kendra Server Endpoints
- `GET /kendra/listIndexes` - List all indexes
- `POST /kendra/query` - Query an index

## Authentication

If you set an API key during deployment:
- Add `X-API-Key: your-key` header to requests
- Or add `?api_key=your-key` query parameter

## Troubleshooting

### Common Issues

1. **Permission Errors**: Ensure your AWS credentials have necessary permissions
2. **Region Mismatch**: Use the same region for both deployments
3. **API Key Issues**: Make sure to use the same key for both servers

### View Logs
```bash
# View S3 server logs
sam logs -n s3-mcp-server --stack-name s3-mcp-stack --tail

# View Kendra server logs
sam logs -n kendra-mcp-server --stack-name kendra-mcp-stack --tail
```

### Update Deployments
```bash
# After making code changes
sam build
sam deploy
```

### Delete Deployments
```bash
# Delete S3 stack
sam delete --stack-name s3-mcp-stack

# Delete Kendra stack
sam delete --stack-name kendra-mcp-stack
```

## Cost Estimation

With moderate usage (1000 requests/month):
- **Lambda**: ~$0.20/month per function
- **API Gateway**: ~$3.50/month per API
- **Total**: ~$7-8/month for both servers

Much cheaper than the $190/month ECS solution!

## Next Steps

1. Test your deployments with curl commands
2. Update your Cline configuration
3. Verify Cline can connect to your AWS Lambda servers
4. Consider adding more authentication or monitoring as needed
