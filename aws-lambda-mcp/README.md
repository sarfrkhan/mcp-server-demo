# AWS Lambda MCP Servers

This directory contains AWS Lambda implementations of MCP (Model Context Protocol) servers that can be deployed to AWS and used remotely by anyone with Cline.

## Overview

The original MCP servers in the `src/` directory run locally. These Lambda versions provide the same functionality but are hosted on AWS, making them accessible to anyone via public API endpoints.

## Available Servers

### S3 MCP Server (`s3-lambda/`)
- **Functionality**: Complete S3 operations (list buckets, get/put/delete objects, etc.)
- **Tools**: listBuckets, createBucket, deleteBucket, listObjects, getObject, putObject, deleteObject
- **Features**: PDF text extraction, base64 encoding support, mutation controls

### Kendra MCP Server (`kendra-lambda/`)
- **Functionality**: Amazon Kendra search and index management
- **Tools**: KendraListIndexesTool, KendraQueryTool
- **Features**: Index listing, document search with relevance scoring

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Cline (Local) │───▶│  API Gateway    │───▶│  Lambda Function│
│                 │    │                 │    │                 │
│ MCP Client      │    │ Public Endpoint │    │ MCP Server Logic│
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

Each MCP server is deployed as:
1. **AWS Lambda Function** - Contains the MCP server logic and AWS service integrations
2. **API Gateway Endpoint** - Provides public HTTPS endpoint that speaks MCP protocol
3. **IAM Role** - Grants necessary AWS service permissions

## Deployment

### Prerequisites
- AWS CLI configured with appropriate credentials
- Python 3.9+ and pip installed
- Bash shell (for deployment scripts)

### Quick Deployment
Deploy all servers at once:
```bash
cd infrastructure/
chmod +x deploy-all.sh
./deploy-all.sh
```

### Individual Server Deployment
Deploy specific servers:
```bash
# S3 Server
cd s3-lambda/
chmod +x deploy.sh
./deploy.sh

# Kendra Server
cd kendra-lambda/
chmod +x deploy.sh
./deploy.sh
```

### Configuration
Edit the deployment scripts to customize:
- `REGION` - AWS region for deployment
- `FUNCTION_NAME` - Lambda function names
- `ROLE_NAME` - IAM role names

## Usage in Cline

After deployment, users can add the API endpoints to their Cline MCP configuration using the **Remote Servers** tab in Cline's MCP interface:

### Method 1: Using Cline's Remote Servers Interface (Recommended)
1. Open Cline in VS Code
2. Click the menu (⋮) in the top right corner of the Cline panel
3. Select "MCP Servers" from the dropdown menu
4. Click on the "Remote Servers" tab
5. Add your servers:
   - **Server Name**: `S3 MCP Server`
   - **Server URL**: `https://API-ID.execute-api.region.amazonaws.com/prod/s3-mcp`
   - Click "Add Server"

### Method 2: Manual Configuration File
Alternatively, you can manually edit the MCP configuration file:

```json
{
  "mcpServers": {
    "s3-server": {
      "url": "https://API-ID.execute-api.region.amazonaws.com/prod/s3-mcp",
      "disabled": false
    },
    "kendra-server": {
      "url": "https://API-ID.execute-api.region.amazonaws.com/prod/kendra-mcp",
      "disabled": false
    }
  }
}
```

**Note**: Replace `API-ID` and `region` with your actual API Gateway ID and AWS region from the deployment output.

The actual API endpoints will be displayed after successful deployment.

## Environment Variables

### S3 Server
- `AWS_REGION` - AWS region (optional, defaults to us-east-1)
- `S3_MCP_READONLY` - Set to 'true' to disable mutation operations

### Kendra Server  
- `AWS_REGION` - AWS region (optional, defaults to us-east-1)
- `KENDRA_INDEX_ID` - Default Kendra index ID for queries

Set environment variables in the Lambda function configuration via AWS Console or CLI.

## Permissions

The deployment scripts create IAM roles with these permissions:

### S3 Server Role
- `AWSLambdaBasicExecutionRole` (managed policy)
- Full S3 access (`s3:*`)

### Kendra Server Role
- `AWSLambdaBasicExecutionRole` (managed policy)
- Kendra read access (`kendra:Query`, `kendra:ListIndices`, `kendra:DescribeIndex`)

## Cost Considerations

### AWS Lambda
- **Free Tier**: 1M requests/month + 400,000 GB-seconds compute
- **Pricing**: ~$0.20 per 1M requests + compute time
- **Memory**: 256MB allocated (adjustable in deploy scripts)
- **Timeout**: 30 seconds (adjustable in deploy scripts)

### API Gateway
- **Free Tier**: 1M API calls/month (first 12 months)
- **Pricing**: ~$3.50 per 1M requests
- **Data Transfer**: Minimal overhead for MCP protocol

### Typical Monthly Cost
For personal use: **Under $5/month**
For moderate team use: **$10-20/month**

## Security

### Current Implementation
- **No authentication** - APIs are publicly accessible
- **CORS enabled** - Allows cross-origin requests
- **HTTPS only** - All traffic encrypted via API Gateway

### Security Enhancements (Optional)
To add authentication, modify the deployment scripts to:
1. Enable API Gateway API keys
2. Add AWS IAM authentication
3. Implement custom authorizers

## Troubleshooting

### Common Issues

1. **Deployment fails with permission errors**
   - Ensure AWS CLI is configured with admin permissions
   - Check IAM user has necessary permissions to create roles/functions

2. **Lambda function timeout**
   - Increase timeout in deployment script (currently 30s)
   - Check CloudWatch logs for specific errors

3. **API Gateway 502 errors**
   - Check Lambda function logs in CloudWatch
   - Verify Lambda function permissions

4. **MCP protocol errors**
   - Test API endpoint directly with curl/Postman
   - Verify JSON-RPC 2.0 format in requests

### Debugging
- Check CloudWatch logs for Lambda functions
- Test API endpoints with tools like curl or Postman
- Use AWS CLI to inspect resource configurations

## Development

### Local Testing
The Lambda functions can be tested locally:
```python
# Test event structure
event = {
    'body': json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/list'
    })
}

# Call handler
result = lambda_handler(event, {})
print(result)
```

### Adding New Tools
1. Add tool function to the Lambda file
2. Update the `tools` dictionary in `MCPServer` class
3. Add tool call handling in `handle_tools_call` method
4. Update IAM permissions if needed
5. Redeploy

## File Structure

```
aws-lambda-mcp/
├── s3-lambda/
│   ├── lambda_function.py      # S3 MCP Lambda implementation
│   ├── requirements.txt        # Python dependencies
│   └── deploy.sh              # S3 deployment script
├── kendra-lambda/
│   ├── lambda_function.py      # Kendra MCP Lambda implementation
│   ├── requirements.txt        # Python dependencies
│   └── deploy.sh              # Kendra deployment script
├── infrastructure/
│   └── deploy-all.sh          # Master deployment script
└── README.md                  # This file
```

## Contributing

When adding new MCP servers:
1. Create new directory under `aws-lambda-mcp/`
2. Follow the same structure as existing servers
3. Create Lambda function with MCP protocol implementation
4. Add deployment script following existing patterns
5. Update master deployment script
6. Document in this README

## Support

For issues related to:
- **AWS deployment**: Check AWS CloudWatch logs and IAM permissions
- **MCP protocol**: Refer to MCP specification documentation
- **Original servers**: See the `src/` directory for local implementations
