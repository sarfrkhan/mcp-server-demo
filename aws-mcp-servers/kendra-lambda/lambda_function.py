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

# Add shared utilities to path
sys.path.append('/opt/python')
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from auth import verify_api_key, create_error_response, create_success_response, get_user_context
from utils import (
    get_aws_client, parse_request_body, get_query_parameters, 
    extract_tool_name_from_path, handle_aws_error, log_request, validate_required_params
)


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
