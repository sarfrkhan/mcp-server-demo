import os
from functools import wraps
from typing import Any, Callable, Dict, Optional
from botocore.config import Config
import boto3

def handle_exceptions(func: Callable) -> Callable:
    """Decorator to handle exceptions in S3 operations.
    Wraps the function in a try-catch and returns {'error': str(e)} on failure."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            return {'error': str(e)}
    return wrapper

def mutation_check(func: Callable) -> Callable:
    """Decorator to block mutations if S3_MCP_READONLY is set to true."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        readonly = os.getenv('S3_MCP_READONLY', '').lower()
        if readonly in ('true', '1', 'yes'):
            return {'error': 'Mutation not allowed: S3_MCP_READONLY is set to true.'}
        return await func(*args, **kwargs)
    return wrapper

def get_s3_client(region_name: Optional[str] = None):
    """Create a boto3 S3 client using credentials from env or AWS config.
    Falls back to AWS_REGION env or default region if not provided."""
    # Determine region: param > AWS_REGION env > default None (boto3 picks default)
    region = region_name or os.getenv('AWS_REGION') or None
    # Custom user agent for MCP
    config = Config(user_agent_extra='MCP/S3Server')
    session = boto3.Session()
    if region:
        return session.client('s3', region_name=region, config=config)
    else:
        return session.client('s3', config=config)

