#!/usr/bin/env python3

import json
import os
import boto3
from typing import Any, Dict, List, Optional
from functools import wraps

# Common utility functions (adapted from original common.py)
def get_kendra_client(region: Optional[str] = None):
    """Create and return a boto3 Kendra client."""
    aws_region = region or os.environ.get('AWS_REGION', 'us-east-1')
    return boto3.client('kendra', region_name=aws_region)

def handle_exceptions(func):
    """Decorator for MCP tool functions: catches exceptions and returns {'error': str(e)}."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return {'error': str(e)}
    return wrapper

# Kendra Tool Functions (adapted from original server.py)
@handle_exceptions
def kendra_list_indexes_tool(region: Optional[str] = None) -> Dict[str, Any]:
    """List all Amazon Kendra indexes in the specified region."""
    # Determine region
    aws_region = region or os.environ.get('AWS_REGION', 'us-east-1')
    client = get_kendra_client(aws_region)
    indexes = []
    
    # Initial list_indices call
    response = client.list_indices()
    items = response.get('IndexConfigurationSummaryItems', [])
    for index in items:
        idx = {
            'id': index.get('Id'),
            'name': index.get('Name'),
            'status': index.get('Status'),
            'created_at': index.get('CreatedAt').isoformat() if index.get('CreatedAt') else None,
            'updated_at': index.get('UpdatedAt').isoformat() if index.get('UpdatedAt') else None,
            'edition': index.get('Edition'),
        }
        indexes.append(idx)
    
    # Pagination
    next_token = response.get('NextToken')
    while next_token:
        response = client.list_indices(NextToken=next_token)
        for index in response.get('IndexConfigurationSummaryItems', []):
            idx = {
                'id': index.get('Id'),
                'name': index.get('Name'),
                'status': index.get('Status'),
                'created_at': index.get('CreatedAt').isoformat() if index.get('CreatedAt') else None,
                'updated_at': index.get('UpdatedAt').isoformat() if index.get('UpdatedAt') else None,
                'edition': index.get('Edition'),
            }
            indexes.append(idx)
        next_token = response.get('NextToken')
    
    return {
        'region': aws_region,
        'count': len(indexes),
        'indexes': indexes,
    }

@handle_exceptions
def kendra_query_tool(
    query: str,
    region: Optional[str] = None,
    index_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Query Amazon Kendra index."""
    aws_region = region or os.environ.get('AWS_REGION', 'us-east-1')
    client = get_kendra_client(aws_region)
    kendra_index_id = index_id or os.environ.get('KENDRA_INDEX_ID')
    
    if not kendra_index_id:
        raise ValueError('KENDRA_INDEX_ID environment variable is not set and no indexId provided.')
    
    response = client.query(IndexId=kendra_index_id, QueryText=query)
    results = {
        'query': query,
        'index_id': kendra_index_id,
        'total_results_count': response.get('TotalNumberOfResults', 0),
        'results': [],
    }
    
    for item in response.get('ResultItems', []):
        result_item: Dict[str, Any] = {
            'id': item.get('Id'),
            'type': item.get('Type'),
            'document_title': item.get('DocumentTitle', {}).get('Text', ''),
            'document_uri': item.get('DocumentURI', ''),
            'score': item.get('ScoreAttributes', {}).get('ScoreConfidence', ''),
        }
        if 'DocumentExcerpt' in item and 'Text' in item['DocumentExcerpt']:
            result_item['excerpt'] = item['DocumentExcerpt']['Text']
        if 'AdditionalAttributes' in item:
            result_item['additional_attributes'] = item['AdditionalAttributes']
        results['results'].append(result_item)
    
    return results

# MCP Protocol Implementation
class MCPServer:
    def __init__(self):
        self.tools = {
            "KendraListIndexesTool": {
                "description": "List all Amazon Kendra indexes in the specified region (or AWS_REGION if not provided). Returns dict with region, count, and indexes list.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "region": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        }
                    }
                }
            },
            "KendraQueryTool": {
                "description": "Query Amazon Kendra index. Returns dict with query, total_results_count, and results list. Requires either indexId param or KENDRA_INDEX_ID env var.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query text"
                        },
                        "region": {
                            "type": "string",
                            "description": "AWS region to use, overrides AWS_REGION env"
                        },
                        "indexId": {
                            "type": "string",
                            "description": "Kendra index ID, overrides KENDRA_INDEX_ID env"
                        }
                    },
                    "required": ["query"]
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
                "name": "kendra-mcp-server",
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
            if name == "KendraListIndexesTool":
                result = kendra_list_indexes_tool(**arguments)
            elif name == "KendraQueryTool":
                result = kendra_query_tool(**arguments)
            else:
                return {"error": f"Unknown tool: {name}"}
            
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except Exception as e:
            return {"error": str(e)}

# Lambda Handler
def lambda_handler(event, context):
    """AWS Lambda handler for MCP Kendra server."""
    try:
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
        
        # Return MCP-formatted response
        response_body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type"
            },
            "body": json.dumps(response_body)
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
        
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps(error_response)
        }
