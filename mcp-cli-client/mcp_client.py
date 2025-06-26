#!/usr/bin/env python3

import json
import requests
import sys
import argparse
from typing import Dict, Any, Optional

class MCPClient:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.session = requests.Session()
        self.request_id = 1
        
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
                "name": "mcp-cli-client",
                "version": "1.0.0"
            }
        })
    
    def list_tools(self) -> Dict[str, Any]:
        """List available tools."""
        return self._make_request("tools/list")
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool."""
        return self._make_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

def print_response(response: Dict[str, Any], indent: int = 0):
    """Pretty print the response."""
    prefix = "  " * indent
    
    if "error" in response:
        print(f"{prefix}❌ Error: {response['error']}")
        return
    
    if "result" in response:
        result = response["result"]
        
        if "error" in result:
            print(f"{prefix}❌ Tool Error: {result['error']}")
            return
            
        if "tools" in result:
            print(f"{prefix}🔧 Available Tools:")
            for tool in result["tools"]:
                print(f"{prefix}  • {tool['name']}: {tool['description']}")
            return
            
        if "content" in result:
            print(f"{prefix}✅ Result:")
            for content in result["content"]:
                if content["type"] == "text":
                    try:
                        data = json.loads(content["text"])
                        print(f"{prefix}  {json.dumps(data, indent=2)}")
                    except:
                        print(f"{prefix}  {content['text']}")
            return
    
    # Fallback: print the whole response
    print(f"{prefix}{json.dumps(response, indent=2)}")

def interactive_mode(client: MCPClient):
    """Interactive mode for the MCP client."""
    print("🚀 MCP CLI Client - Interactive Mode")
    print("Commands: init, tools, call <tool_name>, quit")
    print("=" * 50)
    
    while True:
        try:
            command = input("\n> ").strip()
            
            if command.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            elif command.lower() == 'init':
                print("🔄 Initializing connection...")
                response = client.initialize()
                print_response(response)
            elif command.lower() == 'tools':
                print("📋 Listing tools...")
                response = client.list_tools()
                print_response(response)
            elif command.lower().startswith('call '):
                parts = command.split(' ', 1)
                if len(parts) < 2:
                    print("❌ Usage: call <tool_name>")
                    continue
                    
                tool_name = parts[1]
                print(f"🔧 Calling tool: {tool_name}")
                
                # Get arguments interactively
                print("Enter arguments (JSON format, or press Enter for empty):")
                args_input = input("Args: ").strip()
                
                try:
                    arguments = json.loads(args_input) if args_input else {}
                except json.JSONDecodeError:
                    print("❌ Invalid JSON format")
                    continue
                
                response = client.call_tool(tool_name, arguments)
                print_response(response)
            else:
                print("❌ Unknown command. Available: init, tools, call <tool_name>, quit")
                
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="MCP CLI Client")
    parser.add_argument("server_url", help="MCP server URL")
    parser.add_argument("--tool", help="Tool to call")
    parser.add_argument("--args", help="Tool arguments (JSON format)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    
    args = parser.parse_args()
    
    client = MCPClient(args.server_url)
    
    if args.interactive:
        interactive_mode(client)
    elif args.tool:
        # Single tool call mode
        print(f"🔧 Calling tool: {args.tool}")
        
        try:
            arguments = json.loads(args.args) if args.args else {}
        except json.JSONDecodeError:
            print("❌ Invalid JSON format for arguments")
            sys.exit(1)
        
        # Initialize first
        init_response = client.initialize()
        if "error" in init_response:
            print("❌ Failed to initialize:")
            print_response(init_response)
            sys.exit(1)
        
        # Call the tool
        response = client.call_tool(args.tool, arguments)
        print_response(response)
    else:
        # Default: list tools
        print("📋 Available tools:")
        
        # Initialize first
        init_response = client.initialize()
        if "error" in init_response:
            print("❌ Failed to initialize:")
            print_response(init_response)
            sys.exit(1)
        
        # List tools
        response = client.list_tools()
        print_response(response)

if __name__ == "__main__":
    main()
