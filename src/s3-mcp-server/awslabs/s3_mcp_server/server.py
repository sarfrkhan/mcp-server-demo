#!/usr/bin/env python3

import sys
from loguru import logger
from pydantic import Field
from typing import Optional
import base64
from io import BytesIO
from pypdf import PdfReader

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

getObject supports these parameters:
- BucketName (str): the S3 bucket name.
- Key (str): the object key.
- IsBase64 (bool, default false): if true, always return the object body as a base64-encoded string.
- ExtractText (bool, default false): if true and the object is a PDF (content-type application/pdf or key ends with .pdf), extract and return text; otherwise returns an error if not a PDF.
- region_name (str, optional): override AWS region.

Behavior:
- If ExtractText=true on a PDF: returns {"Text": "...extracted text..."}.
- Otherwise returns {"Body": "..."} and "ContentType": "...". If IsBase64=true, Body is base64. If IsBase64=false but content is binary (e.g., PDF) or non-text, Body is base64; for likely text content, returns UTF-8 string when possible, else base64.
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
extract_text = Field(default=False, description='If true and object is PDF, extract and return text')
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
    ExtractText: bool = extract_text,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """
    Get object content.
    - If ExtractText=true and object is PDF, return {'Text': ...}.
    - Else returns {'Body': ..., 'ContentType': ...}, with Body as text or base64.
    """
    client = get_s3_client(region_name)
    resp = client.get_object(Bucket=BucketName, Key=Key)
    content_type = resp.get("ContentType", "")
    data = resp["Body"].read()
    # Extract text from PDF
    if ExtractText:
        # Check PDF vy content type or file extension
        if content_type.lower() == "application/pdf" or Key.lower().endswith(".pdf"):
            try:
                reader = PdfReader(BytesIO(data))
                pages = []
                for page in reader.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
                full_text = "\n\n".join(pages)
                return {"Text": full_text}
            except Exception as e:
                return {"error": f"Failed to extract PDF text: {e}"}
        else:
            return {"error": "ExtractText=true but object is not detected as PDF"}
    # If not PDF: decide on encoding
    if IsBase64:
        body_str = base64.b64encode(data).decode("utf-8")
    else:
        if content_type.lower() == "application/pdf" or not _is_text_content(content_type, Key):
            body_str = base64.b64encode(data).decode("utf-8")
        else:
            try:
                body_str = data.decode("utf-8")
            except Exception:
                body_str = base64.b64encode(data).decode("utf-8")
    return {"Body": body_str, "ContentType": content_type}

def _is_text_content(content_type: str, key: str) -> bool:
    if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
        return True
    lower = key.lower()
    for ext in (".txt", ".csv", ".json", ".xml", ".md"):
        if lower.endswith(ext):
            return True
    return False

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
    