#!/usr/bin/env python3

import json
import requests
import sys
import argparse
import boto3
from typing import Dict, Any, Optional, List
import re

class MCPClient:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.session = requests.Session()
        self.request_id = 1
        self.tools_cache = None
        
    def _make_request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a JSON-RPC request to the MCP server."""
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        
        self.request_id += 1
        
        try:
            response = self.session.post(
                self.server_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            
            # Handle SSE response format
            if response.headers.get('content-type', '').startswith('text/event-stream'):
                # Parse SSE data
                lines = response.text.strip().split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        data = line[6:]  # Remove 'data: ' prefix
                        return json.loads(data)
            else:
                return response.json()
                
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response: {str(e)}"}
    
    def initialize(self) -> Dict[str, Any]:
        """Initialize the MCP connection."""
        return self._make_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "ai-mcp-client",
                "version": "1.0.0"
            }
        })
    
    def list_tools(self) -> Dict[str, Any]:
        """List available tools."""
        if self.tools_cache is None:
            response = self._make_request("tools/list")
            if "result" in response and "tools" in response["result"]:
                self.tools_cache = response["result"]["tools"]
            return response
        return {"result": {"tools": self.tools_cache}}
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool."""
        return self._make_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

class BedrockAIAgent:
    def __init__(self, region_name: str = "us-east-1"):
        self.bedrock = boto3.client('bedrock-runtime', region_name=region_name)
        self.model_id = "anthropic.claude-3-haiku-20240307-v1:0"  # Fast and cost-effective
        
    def _create_system_prompt(self, tools: List[Dict]) -> str:
        """Create a system prompt with tool descriptions."""
        tools_desc = []
        for tool in tools:
            schema = tool.get('inputSchema', {})
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            tool_desc = f"- **{tool['name']}**: {tool['description']}\n"
            if properties:
                tool_desc += "  Parameters:\n"
                for param, details in properties.items():
                    req_marker = " (required)" if param in required else " (optional)"
                    tool_desc += f"    - {param}{req_marker}: {details.get('description', 'No description')}\n"
            tools_desc.append(tool_desc)
        
        return f"""You are an AI assistant that helps users interact with AWS S3 through MCP (Model Context Protocol) tools. 

Available tools:
{chr(10).join(tools_desc)}

Your job is to:
1. Understand the user's natural language request
2. Determine which tool(s) to call
3. Extract or infer the required parameters
4. Return a JSON response with the tool call(s)

Response format:
{{
    "action": "tool_call",
    "tool": "tool_name",
    "arguments": {{
        "param1": "value1",
        "param2": "value2"
    }},
    "explanation": "Brief explanation of what you're doing"
}}

For multiple operations, use:
{{
    "action": "multiple_tools",
    "tools": [
        {{"tool": "tool1", "arguments": {{}}, "explanation": "..."}},
        {{"tool": "tool2", "arguments": {{}}, "explanation": "..."}}
    ]
}}

If you need clarification or the request is unclear, use:
{{
    "action": "clarification",
    "message": "What specific information do you need?"
}}

Examples:
- "List my buckets" → listBuckets tool
- "Show files in my-bucket" → listObjects with BucketName="my-bucket"
- "Upload hello.txt with content 'Hello World'" → putObject with appropriate parameters
- "Delete file.txt from my-bucket" → deleteObject with BucketName and Key

Be helpful, accurate, and always explain what you're about to do."""

    def process_request(self, user_input: str, tools: List[Dict]) -> Dict[str, Any]:
        """Process user input and determine tool calls."""
        system_prompt = self._create_system_prompt(tools)
        
        messages = [
            {
                "role": "user",
                "content": user_input
            }
        ]
        
        try:
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "system": system_prompt,
                    "messages": messages,
                    "temperature": 0.1
                })
            )
            
            result = json.loads(response['body'].read())
            ai_response = result['content'][0]['text']
            
            # Try to parse JSON response
            try:
                # Extract JSON from the response (handle markdown code blocks)
                json_match = re.search(r'```json\s*(.*?)\s*```', ai_response, re.DOTALL)
                if json_match:
                    ai_response = json_match.group(1)
                elif ai_response.strip().startswith('{'):
                    # Direct JSON response
                    pass
                else:
                    # Look for JSON-like content
                    json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                    if json_match:
                        ai_response = json_match.group(0)
                
                return json.loads(ai_response)
            except json.JSONDecodeError:
                return {
                    "action": "error",
                    "message": f"AI response parsing failed. Raw response: {ai_response}"
                }
                
        except Exception as e:
            return {
                "action": "error",
                "message": f"Bedrock API error: {str(e)}"
            }

class AIMCPClient:
    def __init__(self, server_url: str, region_name: str = "us-east-1"):
        self.mcp_client = MCPClient(server_url)
        self.ai_agent = BedrockAIAgent(region_name)
        self.initialized = False
        
    def initialize(self):
        """Initialize the MCP connection."""
        if not self.initialized:
            init_response = self.mcp_client.initialize()
            if "error" in init_response:
                raise Exception(f"Failed to initialize MCP: {init_response['error']}")
            self.initialized = True
            
    def get_tools(self) -> List[Dict]:
        """Get available tools."""
        tools_response = self.mcp_client.list_tools()
        if "error" in tools_response:
            raise Exception(f"Failed to get tools: {tools_response['error']}")
        return tools_response["result"]["tools"]
    
    def process_natural_language(self, user_input: str) -> str:
        """Process natural language input and execute appropriate tools."""
        try:
            self.initialize()
            tools = self.get_tools()
            
            # Get AI decision
            ai_decision = self.ai_agent.process_request(user_input, tools)
            
            if ai_decision.get("action") == "clarification":
                return f"🤔 {ai_decision['message']}"
            
            elif ai_decision.get("action") == "error":
                return f"❌ {ai_decision['message']}"
            
            elif ai_decision.get("action") == "tool_call":
                return self._execute_single_tool(ai_decision)
            
            elif ai_decision.get("action") == "multiple_tools":
                return self._execute_multiple_tools(ai_decision["tools"])
            
            else:
                return f"❌ Unexpected AI response format: {ai_decision}"
                
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def _execute_single_tool(self, decision: Dict) -> str:
        """Execute a single tool call."""
        tool_name = decision["tool"]
        arguments = decision["arguments"]
        explanation = decision.get("explanation", "")
        
        print(f"🔧 {explanation}")
        print(f"   Calling: {tool_name} with {arguments}")
        
        response = self.mcp_client.call_tool(tool_name, arguments)
        return self._format_tool_response(response, tool_name)
    
    def _execute_multiple_tools(self, tools: List[Dict]) -> str:
        """Execute multiple tool calls."""
        results = []
        for tool_call in tools:
            tool_name = tool_call["tool"]
            arguments = tool_call["arguments"]
            explanation = tool_call.get("explanation", "")
            
            print(f"🔧 {explanation}")
            print(f"   Calling: {tool_name} with {arguments}")
            
            response = self.mcp_client.call_tool(tool_name, arguments)
            result = self._format_tool_response(response, tool_name)
            results.append(result)
        
        return "\n\n".join(results)
    
    def _format_tool_response(self, response: Dict, tool_name: str) -> str:
        """Format tool response for display."""
        if "error" in response:
            return f"❌ Tool Error: {response['error']}"
        
        if "result" in response:
            result = response["result"]
            
            if "error" in result:
                return f"❌ {tool_name} Error: {result['error']}"
            
            if "content" in result:
                try:
                    for content in result["content"]:
                        if content["type"] == "text":
                            data = json.loads(content["text"])
                            return self._format_s3_data(data, tool_name)
                except:
                    return f"✅ {tool_name} completed: {result}"
        
        return f"✅ {tool_name} completed: {json.dumps(response, indent=2)}"
    
    def _format_s3_data(self, data: Dict, tool_name: str) -> str:
        """Format S3-specific data for better readability."""
        if tool_name == "listBuckets" and "Buckets" in data:
            buckets = data["Buckets"]
            if not buckets:
                return "📦 No S3 buckets found in your account."
            
            result = f"📦 Found {len(buckets)} S3 bucket(s):\n"
            for bucket in buckets:
                result += f"   • {bucket['Name']} (created: {bucket['CreationDate']})\n"
            return result.strip()
        
        elif tool_name == "listObjects" and "Contents" in data:
            objects = data["Contents"]
            if not objects:
                return "📁 No objects found in the bucket."
            
            result = f"📁 Found {len(objects)} object(s):\n"
            for obj in objects[:10]:  # Limit to first 10
                size_mb = obj['Size'] / (1024 * 1024)
                result += f"   • {obj['Key']} ({size_mb:.2f} MB, modified: {obj['LastModified']})\n"
            
            if len(objects) > 10:
                result += f"   ... and {len(objects) - 10} more objects\n"
            return result.strip()
        
        elif tool_name == "getObject":
            if "Text" in data:
                return f"📄 Text content:\n{data['Text'][:500]}{'...' if len(data['Text']) > 500 else ''}"
            elif "Body" in data:
                return f"📄 Object retrieved (Content-Type: {data.get('ContentType', 'unknown')})"
        
        elif tool_name in ["createBucket", "putObject", "deleteObject", "deleteBucket"]:
            return f"✅ {tool_name} completed successfully!"
        
        return f"✅ Result: {json.dumps(data, indent=2)}"

def interactive_mode(client: AIMCPClient):
    """Interactive AI mode."""
    print("🤖 AI-Powered MCP Client - Interactive Mode")
    print("Ask me anything about your S3 buckets in natural language!")
    print("Examples:")
    print("  • 'Show me all my buckets'")
    print("  • 'List files in my-data-bucket'")
    print("  • 'Upload hello.txt with content Hello World to my-bucket'")
    print("  • 'Delete old-file.txt from backup-bucket'")
    print("Type 'quit' to exit.")
    print("=" * 60)
    
    while True:
        try:
            user_input = input("\n🗣️  You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if not user_input:
                continue
                
            print("\n🤖 AI Assistant:")
            response = client.process_natural_language(user_input)
            print(response)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="AI-Powered MCP CLI Client")
    parser.add_argument("server_url", help="MCP server URL")
    parser.add_argument("--region", default="us-east-1", help="AWS region for Bedrock")
    parser.add_argument("--query", help="Single natural language query")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    
    args = parser.parse_args()
    
    client = AIMCPClient(args.server_url, args.region)
    
    if args.interactive:
        interactive_mode(client)
    elif args.query:
        print("🤖 Processing your request...")
        response = client.process_natural_language(args.query)
        print(response)
    else:
        print("Please specify --interactive or --query")
        print("Example: python ai_mcp_client.py <server_url> --query 'show me my buckets'")

if __name__ == "__main__":
    main()
