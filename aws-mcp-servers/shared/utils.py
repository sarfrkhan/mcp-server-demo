"""
Common utilities for MCP Lambda servers.
"""
import json
import os
import logging
from typing import Dict, Any, Optional, Union
import boto3
from botocore.exceptions import ClientError, BotoCoreError


# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_aws_client(service_name: str, region_name: Optional[str] = None):
    """
    Get AWS service client with proper error handling.
    """
    try:
        region = region_name or os.environ.get('AWS_REGION', 'us-east-1')
        return boto3.client(service_name, region_name=region)
    except Exception as e:
        logger.error(f"Failed to create {service_name} client: {str(e)}")
        raise


def parse_request_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse request body from API Gateway event.
    """
    body = event.get('body', '{}')
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    return body or {}


def get_path_parameters(event: Dict[str, Any]) -> Dict[str, str]:
    """
    Get path parameters from API Gateway event.
    """
    return event.get('pathParameters') or {}


def get_query_parameters(event: Dict[str, Any]) -> Dict[str, str]:
    """
    Get query string parameters from API Gateway event.
    """
    return event.get('queryStringParameters') or {}


def extract_tool_name_from_path(path: str) -> Optional[str]:
    """
    Extract tool name from API path.
    Example: /s3/listBuckets -> listBuckets
    """
    if not path:
        return None
    
    parts = path.strip('/').split('/')
    if len(parts) >= 2:
        return parts[1]  # Skip service name, get tool name
    return None


def handle_aws_error(error: Exception) -> Dict[str, Any]:
    """
    Handle AWS service errors and return appropriate response.
    """
    if isinstance(error, ClientError):
        error_code = error.response['Error']['Code']
        error_message = error.response['Error']['Message']
        
        # Map common AWS errors to HTTP status codes
        status_code_map = {
            'AccessDenied': 403,
            'NoSuchBucket': 404,
            'NoSuchKey': 404,
            'BucketAlreadyExists': 409,
            'InvalidParameterValue': 400,
            'ValidationException': 400,
            'ResourceNotFoundException': 404,
            'ThrottlingException': 429,
        }
        
        status_code = status_code_map.get(error_code, 500)
        
        return {
            'statusCode': status_code,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': {
                    'type': error_code,
                    'message': error_message,
                    'aws_error': True
                }
            })
        }
    
    # Generic error handling
    return {
        'statusCode': 500,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'error': {
                'type': 'InternalError',
                'message': str(error)
            }
        })
    }


def log_request(event: Dict[str, Any], context: Any = None):
    """
    Log incoming request for debugging.
    """
    logger.info(f"Request: {event.get('httpMethod', 'UNKNOWN')} {event.get('path', 'UNKNOWN')}")
    if context:
        logger.info(f"Request ID: {context.aws_request_id}")


def validate_required_params(params: Dict[str, Any], required: list) -> Optional[str]:
    """
    Validate that required parameters are present.
    Returns error message if validation fails, None if success.
    """
    missing = []
    for param in required:
        if param not in params or params[param] is None:
            missing.append(param)
    
    if missing:
        return f"Missing required parameters: {', '.join(missing)}"
    
    return None


def safe_json_loads(data: str, default: Any = None) -> Any:
    """
    Safely parse JSON string with fallback.
    """
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default
