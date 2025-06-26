#!/usr/bin/env python3

import json
import os
import base64
from io import BytesIO
from typing import Any, Dict, List, Optional
from functools import wraps
import boto3
from botocore.config import Config
from pypdf import PdfReader

# Common utility functions (copied from original common.py)
def handle_exceptions(func):
    """Decorator to handle exceptions in S3 operations."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return {'error': str(e)}
    return wrapper

def mutation_check(func):
    """Decorator to block mutations if S3_MCP_READONLY is set to true."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        readonly = os.getenv('S3_MCP_READONLY', '').lower()
        if readonly in ('true', '1', 'yes'):
            return {'error': 'Mutation not allowed: S3_MCP_READONLY is set to true.'}
        return func(*args, **kwargs)
    return wrapper

def get_s3_client(region_name: Optional[str] = None):
    """Create a boto3 S3 client using credentials from env or AWS config."""
    region = region_name or os.getenv('AWS_REGION') or None
    config = Config(user_agent_extra='MCP/S3Server')
    session = boto3.Session()
    if region:
        return session.client('s3', region_name=region, config=config)
    else:
        return session.client('s3', config=config)

# S3 Tool Functions (adapted from original server.py)
@handle_exceptions
def list_buckets(region_name: Optional[str] = None) -> dict:
    """List all S3 buckets in the account."""
    client = get_s3_client(region_name)
    resp = client.list_buckets()
    buckets = [
        {"Name": b["Name"], "CreationDate": b["CreationDate"].isoformat()}
        for b in resp.get("Buckets", [])
    ]
    return {"Buckets": buckets}

@handle_exceptions
@mutation_check
def create_bucket(
    bucket_name: str,
    acl: Optional[str] = None,
    create_bucket_configuration: Optional[dict] = None,
    region_name: Optional[str] = None,
) -> dict:
    """Create a new S3 bucket. BucketName must be globally unique."""
    client = get_s3_client(region_name)
    params = {"Bucket": bucket_name}
    if acl:
        params["ACL"] = acl
    if create_bucket_configuration:
        params["CreateBucketConfiguration"] = create_bucket_configuration
    resp = client.create_bucket(**params)
    return {"Location": resp.get("Location")}

@handle_exceptions
@mutation_check
def delete_bucket(bucket_name: str, region_name: Optional[str] = None) -> dict:
    """Delete an existing S3 bucket. Bucket must be empty."""
    client = get_s3_client(region_name)
    resp = client.delete_bucket(Bucket=bucket_name)
    return {"ResponseMetadata": resp.get("ResponseMetadata")}

@handle_exceptions
def list_objects(
    bucket_name: str,
    prefix: Optional[str] = None,
    max_keys: Optional[int] = None,
    region_name: Optional[str] = None,
) -> dict:
    """List objects in a bucket, optionally filtered by Prefix."""
    client = get_s3_client(region_name)
    params = {"Bucket": bucket_name}
    if prefix is not None:
        params["Prefix"] = prefix
    if max_keys is not None:
        params["MaxKeys"] = max_keys
    resp = client.list_objects_v2(**params)
    contents = []
    for obj in resp.get("Contents", []):
        contents.append({
            "Key": obj["Key"],
            "LastModified": obj["LastModified"].isoformat(),
            "Size": obj["Size"],
            "ETag": obj["ETag"],
        })
    return {
        "Contents": contents,
        "IsTruncated": resp.get("IsTruncated", False),
        "NextContinuationToken": resp.get("NextContinuationToken"),
    }

@handle_exceptions
def get_object(
    bucket_name: str,
    key: str,
    is_base64: bool = False,
    extract_text: bool = False,
    region_name: Optional[str] = None,
) -> dict:
    """Get object content."""
    client = get_s3_client(region_name)
    resp = client.get_object(Bucket=bucket_name, Key=key)
    content_type = resp.get("ContentType", "")
    data = resp["Body"].read()
    
    # Extract text from PDF
    if extract_text:
        if content_type.lower() == "application/pdf" or key.lower().endswith(".pdf"):
            try:
                reader = PdfReader(BytesIO(data))
                pages = []
                for page in reader.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
                full_text = "\n\n".join(pages)
                return {"Text": full_text}
            except Exception as e:
                return {"error": f"Failed to extract PDF text: {e}"}
        else:
            return {"error": "ExtractText=true but object is not detected as PDF"}
    
    # If not PDF: decide on encoding
    if is_base64:
        body_str = base64.b64encode(data).decode("utf-8")
    else:
        if content_type.lower() == "application/pdf" or not _is_text_content(content_type, key):
            body_str = base64.b64encode(data).decode("utf-8")
        else:
            try:
                body_str = data.decode("utf-8")
            except Exception:
                body_str = base64.b64encode(data).decode("utf-8")
    return {"Body": body_str, "ContentType": content_type}

def _is_text_content(content_type: str, key: str) -> bool:
    if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
        return True
    lower = key.lower()
    for ext in (".txt", ".csv", ".json", ".xml", ".md"):
        if lower.endswith(ext):
            return True
    return False

@handle_exceptions
@mutation_check
def put_object(
    bucket_name: str,
    key: str,
    body: str,
    is_base64: bool = False,
    content_type: Optional[str] = None,
    region_name: Optional[str] = None,
) -> dict:
    """Upload an object. Body is raw text or base64-encoded if IsBase64=true."""
    client = get_s3_client(region_name)
    if is_base64:
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode("utf-8")
    params = {"Bucket": bucket_name, "Key": key, "Body": body_bytes}
    if content_type:
        params["ContentType"] = content_type
    resp = client.put_object(**params)
    return {"ETag": resp.get("ETag"), "VersionId": resp.get("VersionId")}

@handle_exceptions
@mutation_check
def delete_object(
    bucket_name: str,
    key: str,
    region_name: Optional[str] = None,
) -> dict:
    """Delete an object from S3."""
    client = get_s3_client(region_name)
    resp = client.delete_object(Bucket=bucket_name, Key=key)
    return {"ResponseMetadata": resp.get("ResponseMetadata")}

# MCP Protocol Implementation
class MCPServer:
    def __init__(self):
        self.tools = {
            "listBuckets": {
                "description": "List all S3 buckets in the account.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "region_name": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        }
                    }
                }
            },
            "createBucket": {
                "description": "Create a new S3 bucket. BucketName must be globally unique.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "BucketName": {
                            "type": "string",
                            "description": "The name of the S3 bucket"
                        },
                        "ACL": {
                            "type": "string",
                            "description": "Canned ACL for bucket or object, e.g. public-read"
                        },
                        "CreateBucketConfiguration": {
                            "type": "object",
                            "description": "CreateBucketConfiguration, e.g., {\"LocationConstraint\": \"us-west-2\"}"
                        },
                        "region_name": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        }
                    },
                    "required": ["BucketName"]
                }
            },
            "deleteBucket": {
                "description": "Delete an existing S3 bucket. Bucket must be empty.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "BucketName": {
                            "type": "string",
                            "description": "The name of the S3 bucket"
                        },
                        "region_name": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        }
                    },
                    "required": ["BucketName"]
                }
            },
            "listObjects": {
                "description": "List objects in a bucket, optionally filtered by Prefix.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "BucketName": {
                            "type": "string",
                            "description": "The name of the S3 bucket"
                        },
                        "Prefix": {
                            "type": "string",
                            "description": "Key prefix to filter objects"
                        },
                        "MaxKeys": {
                            "type": "integer",
                            "description": "Maximum number of keys to return"
                        },
                        "region_name": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        }
                    },
                    "required": ["BucketName"]
                }
            },
            "getObject": {
                "description": "Get object content. If ExtractText=true and object is PDF, return {'Text': ...}. Else returns {'Body': ..., 'ContentType': ...}, with Body as text or base64.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "BucketName": {
                            "type": "string",
                            "description": "The name of the S3 bucket"
                        },
                        "Key": {
                            "type": "string",
                            "description": "The object key (path) in the bucket"
                        },
                        "IsBase64": {
                            "type": "boolean",
                            "description": "Whether Body is base64-encoded",
                            "default": False
                        },
                        "ExtractText": {
                            "type": "boolean",
                            "description": "If true and object is PDF, extract and return text",
                            "default": False
                        },
                        "region_name": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        }
                    },
                    "required": ["BucketName", "Key"]
                }
            },
            "putObject": {
                "description": "Upload an object. Body is raw text or base64-encoded if IsBase64=true.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "BucketName": {
                            "type": "string",
                            "description": "The name of the S3 bucket"
                        },
                        "Key": {
                            "type": "string",
                            "description": "The object key (path) in the bucket"
                        },
                        "Body": {
                            "type": "string",
                            "description": "Object content as string (raw or base64-encoded)"
                        },
                        "IsBase64": {
                            "type": "boolean",
                            "description": "Whether Body is base64-encoded",
                            "default": False
                        },
                        "ContentType": {
                            "type": "string",
                            "description": "Content-Type of the object"
                        },
                        "region_name": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        }
                    },
                    "required": ["BucketName", "Key", "Body"]
                }
            },
            "deleteObject": {
                "description": "Delete an object from S3.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "BucketName": {
                            "type": "string",
                            "description": "The name of the S3 bucket"
                        },
                        "Key": {
                            "type": "string",
                            "description": "The object key (path) in the bucket"
                        },
                        "region_name": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        }
                    },
                    "required": ["BucketName", "Key"]
                }
            }
        }

    def handle_initialize(self, params: dict) -> dict:
        """Handle MCP initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "s3-mcp-server",
                "version": "1.0.0"
            }
        }

    def handle_tools_list(self) -> dict:
        """Handle MCP tools/list request."""
        tools_list = []
        for name, info in self.tools.items():
            tools_list.append({
                "name": name,
                "description": info["description"],
                "inputSchema": info["inputSchema"]
            })
        return {"tools": tools_list}

    def handle_tools_call(self, name: str, arguments: dict) -> dict:
        """Handle MCP tools/call request."""
        try:
            if name == "listBuckets":
                result = list_buckets(**arguments)
            elif name == "createBucket":
                result = create_bucket(**arguments)
            elif name == "deleteBucket":
                result = delete_bucket(**arguments)
            elif name == "listObjects":
                result = list_objects(**arguments)
            elif name == "getObject":
                result = get_object(**arguments)
            elif name == "putObject":
                result = put_object(**arguments)
            elif name == "deleteObject":
                result = delete_object(**arguments)
            else:
                return {"error": f"Unknown tool: {name}"}
            
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except Exception as e:
            return {"error": str(e)}

# Lambda Handler
def lambda_handler(event, context):
    """AWS Lambda handler for MCP S3 server with SSE transport support."""
    try:
        http_method = event.get('httpMethod', 'POST')
        
        # Handle SSE connection establishment (GET request)
        if http_method == 'GET':
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type"
                },
                "body": "data: {\"type\": \"connection\", \"status\": \"connected\"}\n\n"
            }
        
        # Handle OPTIONS for CORS
        if http_method == 'OPTIONS':
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type"
                },
                "body": ""
            }
        
        # Handle MCP messages (POST request)
        if http_method == 'POST':
            # Parse the request body
            if isinstance(event.get('body'), str):
                body = json.loads(event['body'])
            else:
                body = event.get('body', {})
            
            # Create MCP server instance
            server = MCPServer()
            
            # Handle different MCP methods
            method = body.get('method')
            params = body.get('params', {})
            request_id = body.get('id')
            
            if method == 'initialize':
                result = server.handle_initialize(params)
            elif method == 'tools/list':
                result = server.handle_tools_list()
            elif method == 'tools/call':
                tool_name = params.get('name')
                arguments = params.get('arguments', {})
                result = server.handle_tools_call(tool_name, arguments)
            else:
                result = {"error": f"Unknown method: {method}"}
            
            # Return MCP-formatted response as SSE event
            response_body = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
            
            # Format as Server-Sent Event
            sse_data = f"data: {json.dumps(response_body)}\n\n"
            
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type"
                },
                "body": sse_data
            }
        
        # Unsupported method
        return {
            "statusCode": 405,
            "headers": {
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": "Method not allowed"})
        }
        
    except Exception as e:
        error_response = {
            "jsonrpc": "2.0",
            "id": body.get('id') if 'body' in locals() else None,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }
        
        # Format error as SSE event
        sse_error = f"data: {json.dumps(error_response)}\n\n"
        
        return {
            "statusCode": 200,  # SSE should return 200 even for errors
            "headers": {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*"
            },
            "body": sse_error
        }
