"""
AWS Lambda handler for S3 MCP Server.
Converts the existing S3 MCP server to work with API Gateway and Lambda.
"""
import json
import sys
import os
import base64
from io import BytesIO
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from pypdf import PdfReader

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
            elif error_code in ['NoSuchBucket', 'NoSuchKey']: status_code = 404
            return create_error_response(status_code, error_message, error_code)
        return create_error_response(500, str(error), 'InternalError')
    
    def log_request(event, context=None):
        print(f"Request: {event.get('httpMethod', 'UNKNOWN')} {event.get('path', 'UNKNOWN')}")
    
    def validate_required_params(params, required):
        missing = [param for param in required if param not in params or params[param] is None]
        return f"Missing required parameters: {', '.join(missing)}" if missing else None


def get_s3_client(region_name: Optional[str] = None):
    """Get S3 client with proper region handling."""
    return get_aws_client('s3', region_name)


def _is_text_content(content_type: str, key: str) -> bool:
    """Check if content is likely text-based."""
    if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
        return True
    lower = key.lower()
    for ext in (".txt", ".csv", ".json", ".xml", ".md"):
        if lower.endswith(ext):
            return True
    return False


# S3 Tool Functions (converted from original MCP server)

def list_buckets(params: Dict[str, Any]) -> Dict[str, Any]:
    """List all S3 buckets in the account."""
    region_name = params.get('region_name')
    client = get_s3_client(region_name)
    
    resp = client.list_buckets()
    buckets = [
        {"Name": b["Name"], "CreationDate": b["CreationDate"].isoformat()}
        for b in resp.get("Buckets", [])
    ]
    return {"Buckets": buckets}


def create_bucket(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new S3 bucket."""
    # Validate required parameters
    error = validate_required_params(params, ['BucketName'])
    if error:
        raise ValueError(error)
    
    client = get_s3_client(params.get('region_name'))
    
    create_params = {"Bucket": params['BucketName']}
    if params.get('ACL'):
        create_params["ACL"] = params['ACL']
    if params.get('CreateBucketConfiguration'):
        create_params["CreateBucketConfiguration"] = params['CreateBucketConfiguration']
    
    resp = client.create_bucket(**create_params)
    return {"Location": resp.get("Location")}


def delete_bucket(params: Dict[str, Any]) -> Dict[str, Any]:
    """Delete an existing S3 bucket."""
    error = validate_required_params(params, ['BucketName'])
    if error:
        raise ValueError(error)
    
    client = get_s3_client(params.get('region_name'))
    resp = client.delete_bucket(Bucket=params['BucketName'])
    return {"ResponseMetadata": resp.get("ResponseMetadata")}


def list_objects(params: Dict[str, Any]) -> Dict[str, Any]:
    """List objects in a bucket."""
    error = validate_required_params(params, ['BucketName'])
    if error:
        raise ValueError(error)
    
    client = get_s3_client(params.get('region_name'))
    
    list_params = {"Bucket": params['BucketName']}
    if params.get('Prefix'):
        list_params["Prefix"] = params['Prefix']
    if params.get('MaxKeys'):
        list_params["MaxKeys"] = int(params['MaxKeys'])
    
    resp = client.list_objects_v2(**list_params)
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


def get_object(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get object content."""
    error = validate_required_params(params, ['BucketName', 'Key'])
    if error:
        raise ValueError(error)
    
    client = get_s3_client(params.get('region_name'))
    
    resp = client.get_object(Bucket=params['BucketName'], Key=params['Key'])
    content_type = resp.get("ContentType", "")
    data = resp["Body"].read()
    
    is_base64 = params.get('IsBase64', False)
    extract_text = params.get('ExtractText', False)
    
    # Extract text from PDF
    if extract_text:
        if content_type.lower() == "application/pdf" or params['Key'].lower().endswith(".pdf"):
            try:
                reader = PdfReader(BytesIO(data))
                pages = []
                for page in reader.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
                full_text = "\n\n".join(pages)
                return {"Text": full_text}
            except Exception as e:
                raise ValueError(f"Failed to extract PDF text: {e}")
        else:
            raise ValueError("ExtractText=true but object is not detected as PDF")
    
    # Handle regular content
    if is_base64:
        body_str = base64.b64encode(data).decode("utf-8")
    else:
        if content_type.lower() == "application/pdf" or not _is_text_content(content_type, params['Key']):
            body_str = base64.b64encode(data).decode("utf-8")
        else:
            try:
                body_str = data.decode("utf-8")
            except Exception:
                body_str = base64.b64encode(data).decode("utf-8")
    
    return {"Body": body_str, "ContentType": content_type}


def put_object(params: Dict[str, Any]) -> Dict[str, Any]:
    """Upload an object."""
    error = validate_required_params(params, ['BucketName', 'Key', 'Body'])
    if error:
        raise ValueError(error)
    
    client = get_s3_client(params.get('region_name'))
    
    is_base64 = params.get('IsBase64', False)
    if is_base64:
        body_bytes = base64.b64decode(params['Body'])
    else:
        body_bytes = params['Body'].encode("utf-8")
    
    put_params = {
        "Bucket": params['BucketName'], 
        "Key": params['Key'], 
        "Body": body_bytes
    }
    if params.get('ContentType'):
        put_params["ContentType"] = params['ContentType']
    
    resp = client.put_object(**put_params)
    return {"ETag": resp.get("ETag"), "VersionId": resp.get("VersionId")}


def delete_object(params: Dict[str, Any]) -> Dict[str, Any]:
    """Delete an object from S3."""
    error = validate_required_params(params, ['BucketName', 'Key'])
    if error:
        raise ValueError(error)
    
    client = get_s3_client(params.get('region_name'))
    resp = client.delete_object(Bucket=params['BucketName'], Key=params['Key'])
    return {"ResponseMetadata": resp.get("ResponseMetadata")}


# Tool routing
TOOLS = {
    'listBuckets': list_buckets,
    'createBucket': create_bucket,
    'deleteBucket': delete_bucket,
    'listObjects': list_objects,
    'getObject': get_object,
    'putObject': put_object,
    'deleteObject': delete_object,
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for S3 MCP operations.
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
        
        # Convert string boolean values
        for key, value in params.items():
            if isinstance(value, str):
                if value.lower() == 'true':
                    params[key] = True
                elif value.lower() == 'false':
                    params[key] = False
        
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
