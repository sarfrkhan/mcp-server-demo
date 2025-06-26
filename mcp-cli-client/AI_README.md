# AI-Powered MCP Client with AWS Bedrock

An intelligent command-line client that uses AWS Bedrock (Claude) to understand natural language and automatically interact with your MCP servers. No more remembering tool names or JSON syntax!

## Features

🤖 **Natural Language Processing** - Talk to your S3 buckets in plain English  
🔧 **Automatic Tool Selection** - AI chooses the right tools for you  
📋 **Smart Parameter Extraction** - AI figures out the parameters from context  
✅ **Formatted Responses** - Beautiful, readable output with emojis  
🔄 **Multi-step Operations** - Handle complex workflows automatically  

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Configure AWS credentials (for Bedrock access):
```bash
aws configure
# OR set environment variables:
# export AWS_ACCESS_KEY_ID=your_key
# export AWS_SECRET_ACCESS_KEY=your_secret
# export AWS_DEFAULT_REGION=us-east-1
```

3. Ensure you have Bedrock access:
   - Your AWS account needs access to Claude models in Bedrock
   - The default model is `anthropic.claude-3-haiku-20240307-v1:0`

## Usage

### Interactive Mode (Recommended)

```bash
python ai_mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp --interactive
```

### Single Query Mode

```bash
python ai_mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp --query "show me all my buckets"
```

### Specify AWS Region

```bash
python ai_mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp --region us-west-2 --interactive
```

## Example Conversations

### Interactive Session

```bash
$ python ai_mcp_client.py https://uohegqesb3.execute-api.us-east-1.amazonaws.com/prod/s3-mcp -i

🤖 AI-Powered MCP Client - Interactive Mode
Ask me anything about your S3 buckets in natural language!
Examples:
  • 'Show me all my buckets'
  • 'List files in my-data-bucket'
  • 'Upload hello.txt with content Hello World to my-bucket'
  • 'Delete old-file.txt from backup-bucket'
Type 'quit' to exit.
============================================================

🗣️  You: show me all my buckets

🤖 AI Assistant:
🔧 I'll list all your S3 buckets for you
   Calling: listBuckets with {}
📦 Found 3 S3 bucket(s):
   • my-data-bucket (created: 2025-06-20T10:30:15+00:00)
   • backup-bucket (created: 2025-06-15T14:22:33+00:00)
   • logs-bucket (created: 2025-06-10T09:15:42+00:00)

🗣️  You: what files are in my data bucket?

🤖 AI Assistant:
🔧 I'll list the objects in your my-data-bucket
   Calling: listObjects with {'BucketName': 'my-data-bucket'}
📁 Found 5 object(s):
   • data.csv (2.34 MB, modified: 2025-06-25T16:45:12+00:00)
   • report.pdf (1.87 MB, modified: 2025-06-24T11:30:25+00:00)
   • config.json (0.01 MB, modified: 2025-06-23T08:15:33+00:00)
   • backup/archive.zip (15.67 MB, modified: 2025-06-22T19:20:18+00:00)
   • logs/app.log (0.45 MB, modified: 2025-06-26T07:30:45+00:00)

🗣️  You: upload a file called hello.txt with the content "Hello from AI!" to my data bucket

🤖 AI Assistant:
🔧 I'll upload hello.txt with your specified content to my-data-bucket
   Calling: putObject with {'BucketName': 'my-data-bucket', 'Key': 'hello.txt', 'Body': 'Hello from AI!', 'ContentType': 'text/plain'}
✅ putObject completed successfully!

🗣️  You: delete the config.json file from my data bucket

🤖 AI Assistant:
🔧 I'll delete config.json from your my-data-bucket
   Calling: deleteObject with {'BucketName': 'my-data-bucket', 'Key': 'config.json'}
✅ deleteObject completed successfully!

🗣️  You: quit
👋 Goodbye!
```

## Natural Language Examples

The AI understands various ways to express the same request:

### Listing Buckets
- "Show me all my buckets"
- "List my S3 buckets"
- "What buckets do I have?"
- "Display all buckets"

### Listing Objects
- "What files are in my-bucket?"
- "Show me the contents of data-bucket"
- "List objects in backup-bucket"
- "What's inside my logs bucket?"

### Uploading Files
- "Upload hello.txt with content 'Hello World' to my-bucket"
- "Create a file called data.json in my-bucket with some JSON data"
- "Put a text file named readme.txt in backup-bucket"

### Downloading/Reading Files
- "Show me the content of data.txt from my-bucket"
- "Read the file config.json from my-bucket"
- "Get the contents of report.pdf and extract text"

### Deleting
- "Delete old-file.txt from my-bucket"
- "Remove the backup.zip file from data-bucket"
- "Delete my-bucket (if it's empty)"

### Creating Buckets
- "Create a new bucket called my-new-bucket"
- "Make a bucket named test-bucket in us-west-2"

## AI Capabilities

### Smart Parameter Inference
The AI can infer parameters from context:
- **Bucket names**: Recognizes bucket references like "my data bucket" → "my-data-bucket"
- **File extensions**: Automatically sets ContentType based on file extensions
- **Content types**: Infers appropriate content types for uploads
- **Required vs Optional**: Knows which parameters are required for each tool

### Error Handling
The AI handles various scenarios:
- **Missing information**: Asks for clarification when needed
- **Invalid requests**: Explains what went wrong
- **AWS errors**: Translates technical errors into user-friendly messages

### Multi-step Operations
The AI can handle complex workflows:
- "Copy all .txt files from bucket-a to bucket-b"
- "Create a backup bucket and copy important files there"
- "Clean up old log files from all my buckets"

## Configuration

### AWS Bedrock Models
You can modify the model in `ai_mcp_client.py`:
```python
self.model_id = "anthropic.claude-3-haiku-20240307-v1:0"  # Fast and cheap
# OR
self.model_id = "anthropic.claude-3-sonnet-20240229-v1:0"  # More capable
# OR  
self.model_id = "anthropic.claude-3-opus-20240229-v1:0"    # Most capable
```

### Custom System Prompts
The AI uses carefully crafted system prompts that include:
- Tool descriptions and parameters
- Response format specifications
- Example interactions
- Safety guidelines

## Troubleshooting

### Bedrock Access Issues
```
❌ Error: Bedrock API error: An error occurred (AccessDeniedException)
```
**Solution**: Ensure your AWS account has Bedrock access and the Claude model is enabled.

### AWS Credentials
```
❌ Error: Unable to locate credentials
```
**Solution**: Configure AWS credentials using `aws configure` or environment variables.

### Model Not Available
```
❌ Error: ValidationException: The model ID is not supported
```
**Solution**: Check which Claude models are available in your AWS region.

### MCP Server Connection
```
❌ Error: Request failed: Connection timeout
```
**Solution**: Verify your MCP server URL is correct and accessible.

## Cost Considerations

### AWS Bedrock Pricing (approximate)
- **Claude 3 Haiku**: ~$0.25 per 1M input tokens, ~$1.25 per 1M output tokens
- **Claude 3 Sonnet**: ~$3 per 1M input tokens, ~$15 per 1M output tokens
- **Claude 3 Opus**: ~$15 per 1M input tokens, ~$75 per 1M output tokens

### Typical Usage
- Simple queries: ~100-500 tokens per request
- Complex operations: ~500-1500 tokens per request
- **Estimated cost**: $0.01-0.10 per conversation for Haiku

## Security Considerations

### Data Privacy
- Your natural language queries are sent to AWS Bedrock
- S3 operations are performed using your AWS credentials
- No data is stored permanently by the AI client

### AWS Permissions
The client requires:
- **Bedrock permissions**: `bedrock:InvokeModel`
- **S3 permissions**: Based on what operations you want to perform

### Best Practices
- Use least-privilege AWS credentials
- Monitor Bedrock usage and costs
- Be cautious with destructive operations (deletions)

## Advanced Features

### Custom Tool Integration
You can extend the client to work with other MCP servers:
1. Modify the system prompt to include new tools
2. Add custom response formatting for new data types
3. Update the tool execution logic

### Conversation Context
The AI maintains context within a single session but doesn't persist across sessions. For persistent context, you could extend the client to save conversation history.

### Batch Operations
The AI can handle batch operations by generating multiple tool calls:
```
"Delete all .log files from my-bucket"
→ Lists objects, filters .log files, deletes each one
```

## Contributing

To add new features:
1. **New MCP servers**: Update the system prompt and response formatting
2. **Better AI responses**: Improve the prompt engineering
3. **New output formats**: Add custom formatters for different data types
4. **Error handling**: Add more specific error handling for edge cases

## Examples Repository

Check out these example queries to get started:

### Basic Operations
```bash
python ai_mcp_client.py <server_url> --query "list my buckets"
python ai_mcp_client.py <server_url> --query "show files in my-data-bucket"
python ai_mcp_client.py <server_url> --query "create a bucket called test-bucket"
```

### File Operations
```bash
python ai_mcp_client.py <server_url> --query "upload hello.txt with content 'Hello World' to my-bucket"
python ai_mcp_client.py <server_url> --query "read the file data.txt from my-bucket"
python ai_mcp_client.py <server_url> --query "delete old-file.txt from my-bucket"
```

### Complex Queries
```bash
python ai_mcp_client.py <server_url> --query "show me all PDF files in my documents bucket"
python ai_mcp_client.py <server_url> --query "copy important.txt from bucket-a to bucket-b"
```

This AI-powered client transforms your MCP server into a conversational interface, making cloud operations as easy as having a chat! 🚀
