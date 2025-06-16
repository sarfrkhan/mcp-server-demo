import os
from functools import wraps
from typing import Any, Callable, Dict, Optional
from botocore.config import Config
import boto3

def handle_exceptions(func: Callable) -> Callable:
    """Decorator to handle exceptions in RDS operations.
    Wraps the function and returns {'error': str(e)} on failure."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            return {'error': str(e)}
    return wrapper

def mutation_check(func: Callable) -> Callable:
    """Decorator to block mutations if RDS_MCP_READONLY is set to true."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        readonly = os.getenv('RDS_MCP_READONLY', '').lower()
        if readonly in ('true', '1', 'yes'):
            return {'error': 'Mutation not allowed: RDS_MCP_READONLY is set to true.'}
        return await func(*args, **kwargs)
    return wrapper

def get_rds_client(region_name: Optional[str] = None):
    """Create boto3 RDS client using credentials from env or AWS config.
    Falls back to AWS_REGION env or default if not provided."""
    region = region_name or os.getenv('AWS_REGION') or None
    config = Config(user_agent_extra='MCP/RDSServer')
    session = boto3.Session()
    if region:
        return session.client('rds', region_name=region, config=config)
    else:
        return session.client('rds', config=config)

