"""
AWS Lambda handler for Kendra MCP Server.
Converts the existing Kendra MCP server to work with API Gateway and Lambda.
"""
import json
import sys
import os
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

# Import shared utilities (copied directly into Lambda package)
try:
    from auth import verify_api_key, create_error_response, create_success_response, get_user_context
    from utils import (
        get_aws_client, parse_request_body, get_query_parameters, 
        extract_tool_name_from_path, handle_aws_error, log_request, validate_required_params
    )
except ImportError:
    # Fallback implementations if shared utilities are not available
    def verify_api_key(event):
        return True  # No auth for now
    
    def create_error_response(status_code, message, error_type='Error'):
        return {
            'statusCode': status_code,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': {'type': error_type, 'message': message}})
        }
    
    def create_success_response(data):
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps(data)
        }
    
    def get_aws_client(service_name, region_name=None):
        region = region_name or os.environ.get('AWS_REGION', 'us-east-1')
        return boto3.client(service_name, region_name=region)
    
    def parse_request_body(event):
        body = event.get('body', '{}')
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {}
        return body or {}
    
    def get_query_parameters(event):
        return event.get('queryStringParameters') or {}
    
    def extract_tool_name_from_path(path):
        if not path:
            return None
        parts = path.strip('/').split('/')
        if len(parts) >= 2:
            return parts[1]
        return None
    
    def handle_aws_error(error):
        if isinstance(error, ClientError):
            error_code = error.response['Error']['Code']
            error_message = error.response['Error']['Message']
            status_code = 500
            if error_code in ['AccessDenied']: status_code = 403
            elif error_code in ['ResourceNotFoundException']: status_code = 404
            return create_error_response(status_code, error_message, error_code)
        return create_error_response(500, str(error), 'InternalError')
    
    def log_request(event, context=None):
        print(f"Request: {event.get('httpMethod', 'UNKNOWN')} {event.get('path', 'UNKNOWN')}")
    
    def validate_required_params(params, required):
        missing = [param for param in required if param not in params or params[param] is None]
        return f"Missing required parameters: {', '.join(missing)}" if missing else None


def get_kendra_client(region_name: Optional[str] = None):
    """Get Kendra client with proper region handling."""
    return get_aws_client('kendra', region_name)


# Kendra Tool Functions (converted from original MCP server)

def list_indexes(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all Amazon Kendra indexes in the specified region.
    Returns dict with region, count, and indexes list.
    """
    # Determine region
    aws_region = params.get('region') or os.environ.get('AWS_REGION', 'us-east-1')
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
    
    # Handle pagination
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


def query_index(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query Amazon Kendra index. Returns dict with query, total_results_count, and results list.
    Requires either indexId param or KENDRA_INDEX_ID env var.
    """
    # Validate required parameters
    error = validate_required_params(params, ['query'])
    if error:
        raise ValueError(error)
    
    aws_region = params.get('region') or os.environ.get('AWS_REGION', 'us-east-1')
    client = get_kendra_client(aws_region)
    
    # Get index ID from params or environment
    kendra_index_id = params.get('indexId') or os.environ.get('KENDRA_INDEX_ID')
    if not kendra_index_id:
        raise ValueError('KENDRA_INDEX_ID environment variable is not set and no indexId provided.')
    
    # Execute the query
    response = client.query(IndexId=kendra_index_id, QueryText=params['query'])
    
    results = {
        'query': params['query'],
        'index_id': kendra_index_id,
        'total_results_count': response.get('TotalNumberOfResults', 0),
        'results': [],
    }
    
    # Process result items
    for item in response.get('ResultItems', []):
        result_item = {
            'id': item.get('Id'),
            'type': item.get('Type'),
            'document_title': item.get('DocumentTitle', {}).get('Text', ''),
            'document_uri': item.get('DocumentURI', ''),
            'score': item.get('ScoreAttributes', {}).get('ScoreConfidence', ''),
        }
        
        # Add excerpt if available
        if 'DocumentExcerpt' in item and 'Text' in item['DocumentExcerpt']:
            result_item['excerpt'] = item['DocumentExcerpt']['Text']
        
        # Add additional attributes if available
        if 'AdditionalAttributes' in item:
            result_item['additional_attributes'] = item['AdditionalAttributes']
        
        results['results'].append(result_item)
    
    return results


# Tool routing
TOOLS = {
    'listIndexes': list_indexes,
    'query': query_index,
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Kendra MCP operations.
    """
    try:
        # Log the request
        log_request(event, context)
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
                },
                'body': ''
            }
        
        # Verify authentication
        if not verify_api_key(event):
            return create_error_response(401, 'Unauthorized', 'AuthenticationError')
        
        # Extract tool name from path
        path = event.get('path', '')
        tool_name = extract_tool_name_from_path(path)
        
        if not tool_name or tool_name not in TOOLS:
            return create_error_response(404, f'Tool not found: {tool_name}', 'NotFound')
        
        # Get parameters from request
        params = {}
        
        # Add query parameters
        params.update(get_query_parameters(event))
        
        # Add body parameters for POST/PUT requests
        if event.get('httpMethod') in ['POST', 'PUT']:
            body_params = parse_request_body(event)
            params.update(body_params)
        
        # Execute the tool
        tool_func = TOOLS[tool_name]
        result = tool_func(params)
        
        return create_success_response(result)
        
    except ValueError as e:
        return create_error_response(400, str(e), 'ValidationError')
    except ClientError as e:
        return handle_aws_error(e)
    except Exception as e:
        return create_error_response(500, str(e), 'InternalError')
