#!/usr/bin/env python3
"""
Simple and reliable Streamlit chat UI integrating Amazon Bedrock and local MCP servers.
Uses subprocess calls to avoid event loop conflicts with Streamlit.
"""

import os
import json
import time
import subprocess
import streamlit as st
import boto3
from botocore.exceptions import ClientError

# ------- Configuration -------

DEFAULT_BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "arn:aws:bedrock:us-east-1:864981750171:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0")

# MCP server configurations
MCP_SERVERS = {
    "dynamodb": {
        "command": "C:/Users/sarfrkhan/Desktop/mcp/src/dynamodb-mcp-server/.venv/Scripts/python.exe",
        "args": ["-u", "-m", "awslabs.dynamodb_mcp_server.server"],
        "env": {
            "AWS_PROFILE": os.getenv("AWS_PROFILE", "default"),
            "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        },
    },
    "s3": {
        "command": "C:/Users/sarfrkhan/Desktop/mcp/src/s3-mcp-server/.venv/Scripts/python.exe",
        "args": ["-u", "-m", "awslabs.s3_mcp_server.server"],
        "env": {
            "AWS_PROFILE": os.getenv("AWS_PROFILE", "default"),
            "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        },
    },
    "rds": {
        "command": "C:/Users/sarfrkhan/Desktop/mcp/src/rds-mcp-server/.venv/Scripts/python.exe",
        "args": ["-u", "-m", "awslabs.rds_mcp_server.server"],
        "env": {
            "AWS_PROFILE": os.getenv("AWS_PROFILE", "default"),
            "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        },
    },
}

# Tool to server mapping (discovered from our debug script)
TOOL_TO_SERVER = {
    # DynamoDB tools
    "put_resource_policy": "dynamodb",
    "get_resource_policy": "dynamodb", 
    "scan": "dynamodb",
    "query": "dynamodb",
    "update_item": "dynamodb",
    "get_item": "dynamodb",
    "put_item": "dynamodb",
    "delete_item": "dynamodb",
    "update_time_to_live": "dynamodb",
    "update_table": "dynamodb",
    "list_tables": "dynamodb",
    "create_table": "dynamodb",
    "describe_table": "dynamodb",
    "create_backup": "dynamodb",
    "describe_backup": "dynamodb",
    "list_backups": "dynamodb",
    "restore_table_from_backup": "dynamodb",
    "describe_limits": "dynamodb",
    "describe_time_to_live": "dynamodb",
    "describe_endpoints": "dynamodb",
    "describe_export": "dynamodb",
    "list_exports": "dynamodb",
    "describe_continuous_backups": "dynamodb",
    "untag_resource": "dynamodb",
    "tag_resource": "dynamodb",
    "list_tags_of_resource": "dynamodb",
    "delete_table": "dynamodb",
    "update_continuous_backups": "dynamodb",
    "list_imports": "dynamodb",
    
    # S3 tools
    "listBuckets": "s3",
    "createBucket": "s3",
    "deleteBucket": "s3",
    "listObjects": "s3",
    "getObject": "s3",
    "putObject": "s3",
    "deleteObject": "s3",
    
    # RDS tools
    "describeDBInstances": "rds",
    "createDBInstance": "rds",
    "deleteDBInstance": "rds",
    "describeDBSnapshots": "rds",
    "createDBSnapshot": "rds",
    "deleteDBSnapshot": "rds",
    "restoreDBInstanceFromDBSnapshot": "rds",
    "listTagsForResource": "rds",
    "addTagsToResource": "rds",
    "removeTagsFromResource": "rds",
}

# -----------------------------

st.set_page_config(page_title="Simple Chat with Bedrock + MCP", layout="wide")
st.title(" Simple Chat UI: Amazon Bedrock + MCP Servers")

# Session state for conversation history
if 'conversation' not in st.session_state:
    st.session_state.conversation = []

class SimpleMCPToolCaller:
    """Simple MCP tool caller using subprocess to avoid event loop issues."""
    
    def __init__(self):
        self.server_status = {}
        self._test_connections()
    
    def _test_connections(self):
        """Test if MCP servers are accessible."""
        for server_name, config in MCP_SERVERS.items():
            try:
                # Quick test to see if the server can start
                cmd = [config["command"]] + config["args"]
                env = os.environ.copy()
                env.update(config["env"])
                
                # Start process and test basic communication
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True
                )
                
                # Send a simple initialization message and wait for response
                try:
                    init_msg = '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}}\n'
                    proc.stdin.write(init_msg)
                    proc.stdin.flush()
                    
                    # Try to read a response within timeout
                    response_received = False
                    for _ in range(20):  # 2 second timeout
                        line = proc.stdout.readline()
                        if line and line.strip():
                            try:
                                json.loads(line.strip())
                                response_received = True
                                break
                            except json.JSONDecodeError:
                                continue
                        time.sleep(0.1)
                    
                    self.server_status[server_name] = response_received
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        
                except Exception:
                    self.server_status[server_name] = False
                    try:
                        proc.kill()
                    except:
                        pass
                    
            except Exception as e:
                self.server_status[server_name] = False
    
    def call_tool(self, tool_name: str, params: dict) -> dict:
        """Call an MCP tool using subprocess with proper protocol flow."""
        server_name = TOOL_TO_SERVER.get(tool_name)
        if not server_name:
            return {"error": f"Unknown tool: {tool_name}"}
        
        if not self.server_status.get(server_name, False):
            return {"error": f"Server {server_name} is not available"}
        
        config = MCP_SERVERS[server_name]
        
        try:
            # Prepare the MCP call
            cmd = [config["command"]] + config["args"]
            env = os.environ.copy()
            env.update(config["env"])
            
            # Start the MCP server process
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=0  # Unbuffered for real-time communication
            )
            
            # Step 1: Send initialization message
            init_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "streamlit-client", "version": "1.0"}
                }
            }
            
            proc.stdin.write(json.dumps(init_msg) + "\n")
            proc.stdin.flush()
            
            # Step 2: Wait for initialization response
            init_response = None
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                try:
                    response = json.loads(line.strip())
                    if response.get("id") == 1:
                        init_response = response
                        break
                except json.JSONDecodeError:
                    continue
            
            if not init_response or "error" in init_response:
                proc.terminate()
                return {"error": f"Initialization failed: {init_response.get('error', 'No response')}"}
            
            # Step 3: Send initialized notification
            initialized_msg = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            proc.stdin.write(json.dumps(initialized_msg) + "\n")
            proc.stdin.flush()
            
            # Step 4: Send tool call message
            tool_msg = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": params
                }
            }
            
            proc.stdin.write(json.dumps(tool_msg) + "\n")
            proc.stdin.flush()
            
            # Step 5: Wait for tool call response
            tool_response = None
            timeout_counter = 0
            while timeout_counter < 100:  # 10 second timeout
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    timeout_counter += 1
                    continue
                    
                try:
                    response = json.loads(line.strip())
                    if response.get("id") == 2:
                        tool_response = response
                        break
                except json.JSONDecodeError:
                    continue
                    
                timeout_counter += 1
            
            # Clean up process
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            
            if not tool_response:
                return {"error": "Tool call timed out or no response received"}
            
            if "result" in tool_response:
                # Extract the actual content from MCP response format
                result_data = tool_response["result"]
                if isinstance(result_data, dict) and "content" in result_data:
                    # MCP servers return content in an array format
                    content_items = result_data["content"]
                    if content_items and len(content_items) > 0:
                        # Get the text content from the first item
                        first_item = content_items[0]
                        if isinstance(first_item, dict) and "text" in first_item:
                            try:
                                # Try to parse as JSON if it looks like JSON
                                parsed_content = json.loads(first_item["text"])
                                return {"success": True, "result": parsed_content}
                            except json.JSONDecodeError:
                                # If not JSON, return as text
                                return {"success": True, "result": first_item["text"]}
                        else:
                            return {"success": True, "result": first_item}
                    else:
                        return {"success": True, "result": result_data}
                else:
                    return {"success": True, "result": result_data}
            elif "error" in tool_response:
                return {"success": False, "error": tool_response["error"]}
            else:
                return {"error": "Invalid tool response format"}
            
        except Exception as e:
            if 'proc' in locals():
                try:
                    proc.kill()
                except:
                    pass
            return {"error": f"Tool call failed: {str(e)}"}

# Initialize MCP tool caller
@st.cache_resource
def get_mcp_caller():
    return SimpleMCPToolCaller()

mcp_caller = get_mcp_caller()

# Sidebar: settings for Bedrock and AWS
with st.sidebar:
    st.header("Settings")
    
    # Bedrock model ID
    bedrock_model = st.text_input(
        "Bedrock Model ID",
        value=st.session_state.get("bedrock_model", DEFAULT_BEDROCK_MODEL_ID),
        help="E.g., anthropic.claude-3-5-sonnet-20241022-v2:0"
    )
    st.session_state["bedrock_model"] = bedrock_model

    # AWS profile and region
    st.subheader("AWS Configuration")
    aws_profile = st.text_input(
        "AWS_PROFILE",
        value=os.getenv("AWS_PROFILE", "default"),
        help="AWS profile for credentials"
    )
    aws_region = st.text_input(
        "AWS_REGION",
        value=os.getenv("AWS_REGION", "us-east-1"),
        help="AWS region for API calls"
    )
    
    if aws_profile:
        os.environ["AWS_PROFILE"] = aws_profile
    if aws_region:
        os.environ["AWS_REGION"] = aws_region

    # MCP Server Status
    st.subheader("MCP Server Status")
    for server_name, status in mcp_caller.server_status.items():
        status_text = "Connected" if status else "Disconnected"
        st.text(f"{server_name}: {status_text}")

    # Available Tools
    if st.expander("Available Tools"):
        for server_name in ["dynamodb", "s3", "rds"]:
            tools = [tool for tool, srv in TOOL_TO_SERVER.items() if srv == server_name]
            if tools:
                st.write(f"**{server_name.upper()}:** {len(tools)} tools")
                st.write(f"Examples: {', '.join(tools[:3])}...")

# Display conversation history
for msg in st.session_state.conversation:
    role = msg.get("role", "assistant")
    content = msg.get("content", "")
    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    elif role == "assistant":
        with st.chat_message("assistant"):
            st.markdown(content)
    elif role == "tool":
        with st.chat_message("assistant"):
            st.markdown("**Tool Result:**")
            st.json(content)

# Input box
user_input = st.chat_input("Ask me about your AWS resources...")

def call_bedrock_chat(conversation):
    """Send conversation to Bedrock chat model via boto3."""
    try:
        client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        
        # Prepare messages for modern Claude models
        messages = []
        for msg in conversation:
            if msg["role"] in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # System prompt for tool usage
        system_prompt = f"""You are an AI assistant with access to AWS services through MCP tools. 

        CRITICAL: When the user asks you to perform ANY AWS operation (like listing buckets, tables, instances, etc.), you MUST respond with ONLY the JSON tool call format. Do NOT include any other text.

        Tool call format (respond with ONLY this JSON, nothing else):
        {{"tool": "toolName", "params": {{"param1": "value1"}}}}

        Available tools (use EXACT names):
        S3 tools: listBuckets, createBucket, deleteBucket, listObjects, getObject, putObject, deleteObject
        DynamoDB tools: list_tables, create_table, describe_table, put_item, get_item, update_item, delete_item, scan, query
        RDS tools: describeDBInstances, createDBInstance, deleteDBInstance, describeDBSnapshots, createDBSnapshot

        Examples:
        - User: "list all S3 buckets" → Response: {{"tool": "listBuckets", "params": {{}}}}
        - User: "show me DynamoDB tables" → Response: {{"tool": "list_tables", "params": {{}}}}
        - User: "describe RDS instances" → Response: {{"tool": "describeDBInstances", "params": {{}}}}

        IMPORTANT: 
        1. Use the exact tool names as listed above
        2. For DynamoDB operations, use proper attribute value format like {{"S": "string_value"}} or {{"N": "123"}}
        3. When calling tools, respond with ONLY the JSON - no explanatory text
        """
        
        # Use modern Claude API format
        if "claude-3" in st.session_state["bedrock_model"].lower():
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "temperature": 0.7,
                "messages": messages,
                "system": system_prompt
            }
        else:
            # Fallback for older models
            prompt_parts = [f"System: {system_prompt}"]
            for msg in messages:
                role = "Human" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role}: {msg['content']}")
            prompt_parts.append("Assistant:")
            
            body = {
                "prompt": "\n".join(prompt_parts),
                "max_tokens_to_sample": 4000,
                "temperature": 0.7,
            }

        response = client.invoke_model(
            modelId=st.session_state["bedrock_model"],
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body).encode("utf-8"),
        )
        
        resp_bytes = response["body"].read()
        resp_json = json.loads(resp_bytes)
        
        # Extract response based on model type
        if "claude-3" in st.session_state["bedrock_model"].lower():
            content = resp_json.get("content", [])
            if content and len(content) > 0:
                return content[0].get("text", "")
            else:
                return f"[Bedrock response error] No content in response: {resp_json}"
        else:
            return resp_json.get("completion", "")
            
    except ClientError as e:
        return f"[Bedrock API error] {e}"
    except Exception as e:
        return f"[Bedrock call failed] {e}"

def call_bedrock_analysis(conversation, tool_name, result):
    """Send a simplified conversation to Bedrock for analysis."""
    try:
        client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        
        # Prepare messages for analysis
        messages = []
        for msg in conversation:
            if msg["role"] in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # Add a summary of the tool result instead of the full result
        if result.get("success") and "result" in result:
            if isinstance(result["result"], dict):
                if "Buckets" in result["result"]:
                    summary = f"The tool returned {len(result['result']['Buckets'])} S3 buckets."
                elif "TableNames" in result["result"]:
                    summary = f"The tool returned {len(result['result']['TableNames'])} DynamoDB tables."
                else:
                    summary = "The tool executed successfully and returned data."
            else:
                summary = "The tool executed successfully."
        else:
            summary = f"The tool failed with error: {result.get('error', 'Unknown error')}"
        
        messages.append({"role": "assistant", "content": summary})
        
        # Simple analysis prompt
        system_prompt = """You are an AI assistant. The user asked for AWS data and I executed a tool to get it. 
        Provide a brief, helpful summary of what was found. Keep it concise and user-friendly.
        Do not repeat the raw data - just summarize what was discovered."""
        
        # Use modern Claude API format
        if "claude-3" in st.session_state["bedrock_model"].lower():
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,  # Shorter response
                "temperature": 0.3,  # Less creative
                "messages": messages,
                "system": system_prompt
            }
        else:
            # Fallback for older models
            prompt_parts = [f"System: {system_prompt}"]
            for msg in messages:
                role = "Human" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role}: {msg['content']}")
            prompt_parts.append("Assistant:")
            
            body = {
                "prompt": "\n".join(prompt_parts),
                "max_tokens_to_sample": 500,
                "temperature": 0.3,
            }

        response = client.invoke_model(
            modelId=st.session_state["bedrock_model"],
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body).encode("utf-8"),
        )
        
        resp_bytes = response["body"].read()
        resp_json = json.loads(resp_bytes)
        
        # Extract response based on model type
        if "claude-3" in st.session_state["bedrock_model"].lower():
            content = resp_json.get("content", [])
            if content and len(content) > 0:
                return content[0].get("text", "")
            else:
                return f"[Bedrock analysis error] No content in response"
        else:
            return resp_json.get("completion", "")
            
    except Exception as e:
        return f"[Bedrock analysis failed] {e}"

def detect_and_call_tool(response_text):
    """Parse assistant response for tool calls."""
    # First try to parse the entire response as JSON
    try:
        parsed = json.loads(response_text.strip())
        if isinstance(parsed, dict) and "tool" in parsed and "params" in parsed:
            return parsed["tool"], parsed["params"]
    except json.JSONDecodeError:
        pass
    
    # If that fails, look for JSON within the text
    import re
    json_pattern = r'\{[^{}]*"tool"[^{}]*"params"[^{}]*\}'
    matches = re.findall(json_pattern, response_text)
    
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict) and "tool" in parsed and "params" in parsed:
                return parsed["tool"], parsed["params"]
        except json.JSONDecodeError:
            continue
    
    # More flexible pattern to catch JSON that might span multiple lines
    json_pattern_multiline = r'\{[^{}]*?"tool"[^{}]*?"params"[^{}]*?\}'
    matches = re.findall(json_pattern_multiline, response_text, re.DOTALL)
    
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict) and "tool" in parsed and "params" in parsed:
                return parsed["tool"], parsed["params"]
        except json.JSONDecodeError:
            continue
    
    return None, None

# Main: when user submits input
if user_input:
    # Append and display user message
    st.session_state.conversation.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # First Bedrock call
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            resp = call_bedrock_chat(st.session_state.conversation)
        
        # Display response with typing effect
        placeholder = st.empty()
        collected = ""
        for token in resp.split():
            collected += token + " "
            placeholder.markdown(collected + "▌")
            time.sleep(0.02)
        placeholder.markdown(collected)
        assistant_message = collected.strip()

        # Append assistant reply
        st.session_state.conversation.append({"role": "assistant", "content": assistant_message})

        # Detect tool invocation
        tool_name, tool_params = detect_and_call_tool(assistant_message)
        if tool_name:
            st.markdown(f"**Calling tool:** `{tool_name}`")
            
            with st.spinner(f"Executing {tool_name}..."):
                result = mcp_caller.call_tool(tool_name, tool_params)
            
            # Display and append tool result
            st.markdown("**Tool Result:**")
            st.json(result)
            st.session_state.conversation.append({"role": "tool", "content": result})

            # Follow-up Bedrock call with updated conversation
            with st.spinner("Analyzing results..."):
                # Create a simplified conversation for analysis to avoid token limits
                analysis_conversation = [
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": f"I executed the {tool_name} tool and got the following results:"},
                    {"role": "tool", "content": result}
                ]
                resp2 = call_bedrock_analysis(analysis_conversation, tool_name, result)
            
            if not resp2.startswith("[Bedrock"):  # Only show analysis if no error
                st.markdown("**Analysis:**")
                placeholder2 = st.empty()
                collected2 = ""
                for token in resp2.split():
                    collected2 += token + " "
                    placeholder2.markdown(collected2 + "▌")
                    time.sleep(0.02)
                placeholder2.markdown(collected2)
                
                assistant_followup = collected2.strip()
                st.session_state.conversation.append({"role": "assistant", "content": assistant_followup})
            else:
                # If analysis fails, provide a simple summary
                if result.get("success"):
                    summary = f"Successfully executed {tool_name}. "
                    if "result" in result:
                        if isinstance(result["result"], dict):
                            if "Buckets" in result["result"]:
                                bucket_count = len(result["result"]["Buckets"])
                                summary += f"Found {bucket_count} S3 buckets in your account."
                            elif "TableNames" in result["result"]:
                                table_count = len(result["result"]["TableNames"])
                                summary += f"Found {table_count} DynamoDB tables in your account."
                            else:
                                summary += "Data retrieved successfully."
                        else:
                            summary += "Operation completed successfully."
                    st.markdown(f"**Summary:** {summary}")
                    st.session_state.conversation.append({"role": "assistant", "content": summary})
                else:
                    error_msg = f"Tool execution failed: {result.get('error', 'Unknown error')}"
                    st.markdown(f"**Error:** {error_msg}")
                    st.session_state.conversation.append({"role": "assistant", "content": error_msg})

    # Rerun to refresh UI
    st.rerun()
