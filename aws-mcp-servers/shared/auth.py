"""
Authentication utilities for MCP Lambda servers.
"""
import json
import os
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError


def verify_api_key(event: Dict[str, Any]) -> bool:
    """
    Simple API key authentication.
    Checks for API key in headers or query parameters.
    """
    # Get API key from environment
    expected_key = os.environ.get('MCP_API_KEY')
    if not expected_key:
        # If no API key is set, allow all requests (development mode)
        return True
    
    # Check headers first
    headers = event.get('headers', {})
    api_key = headers.get('x-api-key') or headers.get('X-API-Key')
    
    # Check query parameters if not in headers
    if not api_key:
        query_params = event.get('queryStringParameters') or {}
        api_key = query_params.get('api_key')
    
    return api_key == expected_key


def get_user_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract user context from the request.
    Can be extended to support Cognito JWT tokens.
    """
    headers = event.get('headers', {})
    return {
        'user_agent': headers.get('User-Agent', 'unknown'),
        'source_ip': event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown'),
        'request_id': event.get('requestContext', {}).get('requestId', 'unknown')
    }


def create_error_response(status_code: int, message: str, error_type: str = 'Error') -> Dict[str, Any]:
    """
    Create a standardized error response.
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'error': {
                'type': error_type,
                'message': message
            }
        })
    }


def create_success_response(data: Any) -> Dict[str, Any]:
    """
    Create a standardized success response.
    """
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(data)
    }
