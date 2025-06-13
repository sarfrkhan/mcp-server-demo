#!/usr/bin/env python3

import sys
from loguru import logger
from pydantic import Field
from typing import Optional
import base64

from mcp.server.fastmcp import FastMCP
from awslabs.s3_mcp_server.common import (
    handle_exceptions,
    mutation_check,
    get_s3_client,
)

app = FastMCP(
    name='s3-server',
    instructions="""MCP Server for interacting with AWS S3.

Supported operations: listBuckets, createBucket, deleteBucket, listObjects, getObject, putObject, deleteObject.

- Bucket names must be globally unique when creating.
- For getObject/putObject: bodies may be base64-encoded if IsBase64=true.
""",
    version='0.1.0',
)

# Common parameter fields
bucket_name = Field(description='The name of the S3 bucket')
key = Field(description='The object key (path) in the bucket')
prefix = Field(default=None, description='Key prefix to filter objects')
max_keys = Field(default=None, description='Maximum number of keys to return')
body = Field(description='Object content as string (raw or base64-encoded)')
is_base64 = Field(default=False, description='Whether Body is base64-encoded')
content_type = Field(default=None, description='Content-Type of the object')
acl = Field(default=None, description='Canned ACL for bucket or object, e.g. public-read')
create_bucket_config = Field(default=None, description='CreateBucketConfiguration, e.g., {"LocationConstraint": "us-west-2"}')
region_name_param = Field(default=None, description='AWS region to use, overrides AWS_REGION env')

@app.tool()
@handle_exceptions
async def listBuckets(
    region_name: Optional[str] = region_name_param,
) -> dict:
    """List all S3 buckets in the account."""
    client = get_s3_client(region_name)
    resp = client.list_buckets()
    buckets = [
        {"Name": b["Name"], "CreationDate": b["CreationDate"].isoformat()}
        for b in resp.get("Buckets", [])
    ]
    return {"Buckets": buckets}

@app.tool()
@handle_exceptions
@mutation_check
async def createBucket(
    BucketName: str = bucket_name,
    ACL: Optional[str] = acl,
    CreateBucketConfiguration: Optional[dict] = create_bucket_config,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Create a new S3 bucket. BucketName must be globally unique."""
    client = get_s3_client(region_name)
    params = {"Bucket": BucketName}
    if ACL:
        params["ACL"] = ACL
    if CreateBucketConfiguration:
        params["CreateBucketConfiguration"] = CreateBucketConfiguration
    resp = client.create_bucket(**params)
    # Location header may or may not be present
    return {"Location": resp.get("Location")}

@app.tool()
@handle_exceptions
@mutation_check
async def deleteBucket(
    BucketName: str = bucket_name,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Delete an existing S3 bucket. Bucket must be empty."""
    client = get_s3_client(region_name)
    resp = client.delete_bucket(Bucket=BucketName)
    return {"ResponseMetadata": resp.get("ResponseMetadata")}

@app.tool()
@handle_exceptions
async def listObjects(
    BucketName: str = bucket_name,
    Prefix: Optional[str] = prefix,
    MaxKeys: Optional[int] = max_keys,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """List objects in a bucket, optionally filtered by Prefix."""
    client = get_s3_client(region_name)
    params = {"Bucket": BucketName}
    if Prefix is not None:
        params["Prefix"] = Prefix
    if MaxKeys is not None:
        params["MaxKeys"] = MaxKeys
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

@app.tool()
@handle_exceptions
async def getObject(
    BucketName: str = bucket_name,
    Key: str = key,
    IsBase64: bool = is_base64,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Get object content. If IsBase64=true, returns base64-encoded body."""
    client = get_s3_client(region_name)
    resp = client.get_object(Bucket=BucketName, Key=Key)
    data = resp["Body"].read()
    if IsBase64:
        body_str = base64.b64encode(data).decode("utf-8")
    else:
        try:
            body_str = data.decode("utf-8")
        except Exception:
            # Binary data fallback
            body_str = base64.b64encode(data).decode("utf-8")
    return {"Body": body_str, "ContentType": resp.get("ContentType")}

@app.tool()
@handle_exceptions
@mutation_check
async def putObject(
    BucketName: str = bucket_name,
    Key: str = key,
    Body: str = body,
    IsBase64: bool = is_base64,
    ContentType: Optional[str] = content_type,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Upload an object. Body is raw text or base64-encoded if IsBase64=true."""
    client = get_s3_client(region_name)
    if IsBase64:
        body_bytes = base64.b64decode(Body)
    else:
        body_bytes = Body.encode("utf-8")
    params = {"Bucket": BucketName, "Key": Key, "Body": body_bytes}
    if ContentType:
        params["ContentType"] = ContentType
    resp = client.put_object(**params)
    return {"ETag": resp.get("ETag"), "VersionId": resp.get("VersionId")}

@app.tool()
@handle_exceptions
@mutation_check
async def deleteObject(
    BucketName: str = bucket_name,
    Key: str = key,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Delete an object from S3."""
    client = get_s3_client(region_name)
    resp = client.delete_object(Bucket=BucketName, Key=Key)
    return {"ResponseMetadata": resp.get("ResponseMetadata")}

def main():
    """Main entry point for S3 MCP Server."""
    # Print startup for confirmation
    print(">>> S3 MCP Server starting up...", flush=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    app.run()

if __name__ == '__main__':
    main()
    