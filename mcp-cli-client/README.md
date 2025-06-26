# MCP CLI Client

A command-line client for interacting with MCP (Model Context Protocol) servers, specifically designed to work with our AWS Lambda MCP servers.

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Make the script executable (optional):
```bash
chmod +x mcp_client.py
```

## Usage

### Basic Usage - List Available Tools

```bash
python mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp
```

### Interactive Mode

```bash
python mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp --interactive
```

In interactive mode, you can use these commands:
- `init` - Initialize connection with the server
- `tools` - List available tools
- `call <tool_name>` - Call a specific tool (will prompt for arguments)
- `quit` - Exit the client

### Single Tool Call

```bash
# List S3 buckets
python mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp --tool listBuckets

# List objects in a bucket
python mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp --tool listObjects --args '{"BucketName": "my-bucket"}'

# Get an object
python mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp --tool getObject --args '{"BucketName": "my-bucket", "Key": "my-file.txt"}'

# Create a bucket
python mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp --tool createBucket --args '{"BucketName": "my-new-bucket"}'
```

## Available S3 Tools

- **listBuckets** - List all S3 buckets in your account
- **createBucket** - Create a new S3 bucket
- **deleteBucket** - Delete an empty S3 bucket
- **listObjects** - List objects in a bucket
- **getObject** - Download/read an object from S3
- **putObject** - Upload/write an object to S3
- **deleteObject** - Delete an object from S3

## Interactive Mode Example

```bash
$ python mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp -i

🚀 MCP CLI Client - Interactive Mode
Commands: init, tools, call <tool_name>, quit
==================================================

> init
🔄 Initializing connection...
✅ Result:
  {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {}
    },
    "serverInfo": {
      "name": "s3-mcp-server",
      "version": "1.0.0"
    }
  }

> tools
📋 Listing tools...
🔧 Available Tools:
  • listBuckets: List all S3 buckets in the account.
  • createBucket: Create a new S3 bucket. BucketName must be globally unique.
  • deleteBucket: Delete an existing S3 bucket. Bucket must be empty.
  • listObjects: List objects in a bucket, optionally filtered by Prefix.
  • getObject: Get object content.
  • putObject: Upload an object. Body is raw text or base64-encoded if IsBase64=true.
  • deleteObject: Delete an object from S3.

> call listBuckets
🔧 Calling tool: listBuckets
Enter arguments (JSON format, or press Enter for empty):
Args: 
✅ Result:
  {
    "Buckets": [
      {
        "Name": "my-test-bucket",
        "CreationDate": "2025-06-26T08:30:15+00:00"
      }
    ]
  }

> quit
👋 Goodbye!
```

## Error Handling

The client handles various error scenarios:
- Network connectivity issues
- Invalid JSON responses
- Server errors
- Invalid tool arguments

All errors are displayed with clear error messages and appropriate emoji indicators.

## Features

- 🚀 **Easy to use** - Simple command-line interface
- 🔧 **Interactive mode** - Chat-like interface for exploring tools
- 📋 **Tool discovery** - Automatically lists available tools
- ✅ **Pretty output** - Formatted JSON responses with emoji indicators
- ❌ **Error handling** - Clear error messages and graceful failure handling
- 🔄 **SSE support** - Handles Server-Sent Events responses from Lambda

## Troubleshooting

### Connection Issues
- Ensure your AWS Lambda endpoint is correct and accessible
- Check that your AWS credentials are properly configured if the Lambda requires authentication

### Tool Errors
- Verify that your tool arguments are in valid JSON format
- Check that required parameters are provided
- Ensure you have proper AWS permissions for the operations you're trying to perform

### JSON Format Examples
```json
// Simple arguments
{"BucketName": "my-bucket"}

// Multiple arguments
{"BucketName": "my-bucket", "Key": "path/to/file.txt"}

// Complex arguments
{
  "BucketName": "my-bucket",
  "Key": "data.json",
  "Body": "{\"message\": \"Hello World\"}",
  "ContentType": "application/json"
}
