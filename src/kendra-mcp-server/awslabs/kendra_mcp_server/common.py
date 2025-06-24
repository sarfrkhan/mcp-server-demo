import os
import boto3
from mypy_boto3_kendra.client import KendraClient
from functools import wraps
from typing import Callable, Any, Dict

def get_kendra_client(region: str | None = None) -> KendraClient:
    """
    Create and return a boto3 Kendra client.
    Respects AWS_PROFILE env var and AWS_REGION or passed-in region.
    """
    aws_profile = os.environ.get('AWS_PROFILE')
    aws_region = region or os.environ.get('AWS_REGION', 'us-east-1')
    if aws_profile:
        session = boto3.Session(profile_name=aws_profile, region_name=aws_region)
        return session.client('kendra')
    return boto3.client('kendra', region_name=aws_region)

def handle_exceptions(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for MCP tool functions: catches exceptions and returns {'error': str(e)}.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            return {'error': str(e)}
    return wrapper