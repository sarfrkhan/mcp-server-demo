#!/usr/bin/env python3

import sys
from loguru import logger
from pydantic import Field
from typing import Optional, List, Dict
from mcp.server.fastmcp import FastMCP
from awslabs.rds_mcp_server.common import handle_exceptions, mutation_check, get_rds_client

app = FastMCP(
    name='rds-server',
    instructions="""MCP Server for interacting with AWS RDS.

Supported operations include describeDBInstances, createDBInstance, deleteDBInstance, describeDBSnapshots, createDBSnapshot, deleteDBSnapshot, restoreDBInstanceFromDBSnapshot, listTagsForResource, addTagsToResource, removeTagsFromResource.

Note: create/delete operations are asynchronous and may take time—use describeDBInstances to poll status. Tag operations require correct ARN format for ResourceName.""",
    version='0.1.0',
)

# Common parameter fields
db_instance_id = Field(description='The RDS DB instance identifier')
db_instance_class = Field(description='The compute and memory capacity class, e.g., db.t3.micro')
engine = Field(description='The database engine, e.g., mysql, postgres')
master_username = Field(description='Master username for the DB instance')
master_password = Field(description='Master user password for the DB instance')
allocated_storage = Field(default=None, description='Allocated storage in GiB for createDBInstance')
skip_final_snapshot = Field(default=True, description='Whether to skip final snapshot when deleting')
final_snapshot_id = Field(default=None, description='Identifier for final DB snapshot if not skipping')
snapshot_id = Field(description='The DB snapshot identifier')
resource_arn = Field(description='ARN of the RDS resource (instance or snapshot) for tagging')
tags = Field(description='List of tags as [{"Key":..., "Value":...}]')
tag_keys = Field(description='List of tag keys to remove')
region_name_param = Field(default=None, description='AWS region to use, overrides AWS_REGION env')

@app.tool()
@handle_exceptions
async def describeDBInstances(
    DBInstanceIdentifier: Optional[str] = Field(default=None, description='If provided, returns info for this instance'),
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Describe one or all RDS DB instances."""
    client = get_rds_client(region_name)
    if DBInstanceIdentifier:
        resp = client.describe_db_instances(DBInstanceIdentifier=DBInstanceIdentifier)
    else:
        resp = client.describe_db_instances()
    instances = []
    for inst in resp.get("DBInstances", []):
        instances.append({
            "DBInstanceIdentifier": inst.get("DBInstanceIdentifier"),
            "DBInstanceStatus": inst.get("DBInstanceStatus"),
            "Engine": inst.get("Engine"),
            "DBInstanceClass": inst.get("DBInstanceClass"),
            "Endpoint": inst.get("Endpoint", {}).get("Address"),
            "AllocatedStorage": inst.get("AllocatedStorage"),
        })
    return {"DBInstances": instances}

@app.tool()
@handle_exceptions
@mutation_check
async def createDBInstance(
    DBInstanceIdentifier: str = db_instance_id,
    DBInstanceClass: str = db_instance_class,
    Engine: str = engine,
    MasterUsername: str = master_username,
    MasterUserPassword: str = master_password,
    AllocatedStorage: Optional[int] = allocated_storage,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Create a new RDS DB instance. Note: may take minutes."""
    client = get_rds_client(region_name)
    params = {
        "DBInstanceIdentifier": DBInstanceIdentifier,
        "DBInstanceClass": DBInstanceClass,
        "Engine": Engine,
        "MasterUsername": MasterUsername,
        "MasterUserPassword": MasterUserPassword,
    }
    if AllocatedStorage:
        params["AllocatedStorage"] = AllocatedStorage
    resp = client.create_db_instance(**params)
    inst = resp.get("DBInstance", {})
    return {
        "DBInstance": {
            "DBInstanceIdentifier": inst.get("DBInstanceIdentifier"),
            "DBInstanceStatus": inst.get("DBInstanceStatus")
        }
    }

@app.tool()
@handle_exceptions
@mutation_check
async def deleteDBInstance(
    DBInstanceIdentifier: str = db_instance_id,
    SkipFinalSnapshot: bool = skip_final_snapshot,
    FinalDBSnapshotIdentifier: Optional[str] = final_snapshot_id,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Delete an RDS DB instance. If SkipFinalSnapshot=false, FinalDBSnapshotIdentifier is required."""
    client = get_rds_client(region_name)
    if SkipFinalSnapshot:
        resp = client.delete_db_instance(DBInstanceIdentifier=DBInstanceIdentifier, SkipFinalSnapshot=True)
    else:
        if not FinalDBSnapshotIdentifier:
            raise ValueError("FinalDBSnapshotIdentifier must be provided if SkipFinalSnapshot is false")
        resp = client.delete_db_instance(
            DBInstanceIdentifier=DBInstanceIdentifier,
            SkipFinalSnapshot=False,
            FinalDBSnapshotIdentifier=FinalDBSnapshotIdentifier
        )
    inst = resp.get("DBInstance", {})
    return {
        "DBInstance": {
            "DBInstanceIdentifier": inst.get("DBInstanceIdentifier"),
            "DBInstanceStatus": inst.get("DBInstanceStatus")
        }
    }

@app.tool()
@handle_exceptions
async def describeDBSnapshots(
    DBInstanceIdentifier: Optional[str] = Field(default=None, description='If provided, filter snapshots by this instance'),
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Describe DB snapshots."""
    client = get_rds_client(region_name)
    params: Dict = {}
    if DBInstanceIdentifier:
        params["DBInstanceIdentifier"] = DBInstanceIdentifier
    resp = client.describe_db_snapshots(**params)
    snaps = []
    for snap in resp.get("DBSnapshots", []):
        snaps.append({
            "DBSnapshotIdentifier": snap.get("DBSnapshotIdentifier"),
            "DBInstanceIdentifier": snap.get("DBInstanceIdentifier"),
            "Status": snap.get("Status"),
            "SnapshotCreateTime": snap.get("SnapshotCreateTime").isoformat() if snap.get("SnapshotCreateTime") else None
        })
    return {"DBSnapshots": snaps}

@app.tool()
@handle_exceptions
@mutation_check
async def createDBSnapshot(
    DBInstanceIdentifier: str = db_instance_id,
    DBSnapshotIdentifier: str = snapshot_id,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Create a DB snapshot for the given instance."""
    client = get_rds_client(region_name)
    resp = client.create_db_snapshot(DBInstanceIdentifier=DBInstanceIdentifier, DBSnapshotIdentifier=DBSnapshotIdentifier)
    snap = resp.get("DBSnapshot", {})
    return {
        "DBSnapshot": {
            "DBSnapshotIdentifier": snap.get("DBSnapshotIdentifier"),
            "Status": snap.get("Status")
        }
    }

@app.tool()
@handle_exceptions
@mutation_check
async def deleteDBSnapshot(
    DBSnapshotIdentifier: str = snapshot_id,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Delete a DB snapshot."""
    client = get_rds_client(region_name)
    resp = client.delete_db_snapshot(DBSnapshotIdentifier=DBSnapshotIdentifier)
    # delete_db_snapshot returns metadata
    return {"ResponseMetadata": resp.get("ResponseMetadata")}

@app.tool()
@handle_exceptions
@mutation_check
async def restoreDBInstanceFromDBSnapshot(
    DBInstanceIdentifier: str = db_instance_id,
    DBSnapshotIdentifier: str = snapshot_id,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Restore a new DB instance from a snapshot. New instance uses DBInstanceIdentifier."""
    client = get_rds_client(region_name)
    resp = client.restore_db_instance_from_db_snapshot(
        DBInstanceIdentifier=DBInstanceIdentifier,
        DBSnapshotIdentifier=DBSnapshotIdentifier
    )
    inst = resp.get("DBInstance", {})
    return {
        "DBInstance": {
            "DBInstanceIdentifier": inst.get("DBInstanceIdentifier"),
            "DBInstanceStatus": inst.get("DBInstanceStatus")
        }
    }

@app.tool()
@handle_exceptions
async def listTagsForResource(
    ResourceName: str = resource_arn,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """List tags for an RDS resource ARN."""
    client = get_rds_client(region_name)
    resp = client.list_tags_for_resource(ResourceName=ResourceName)
    return {"TagList": resp.get("TagList", [])}

@app.tool()
@handle_exceptions
@mutation_check
async def addTagsToResource(
    ResourceName: str = resource_arn,
    Tags: List[Dict[str, str]] = tags,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Add tags to an RDS resource ARN."""
    client = get_rds_client(region_name)
    resp = client.add_tags_to_resource(ResourceName=ResourceName, Tags=Tags)
    return {"TagList": resp.get("TagList", [])}

@app.tool()
@handle_exceptions
@mutation_check
async def removeTagsFromResource(
    ResourceName: str = resource_arn,
    TagKeys: List[str] = tag_keys,
    region_name: Optional[str] = region_name_param,
) -> dict:
    """Remove tags from an RDS resource ARN."""
    client = get_rds_client(region_name)
    resp = client.remove_tags_from_resource(ResourceName=ResourceName, TagKeys=TagKeys)
    return {"ResponseMetadata": resp.get("ResponseMetadata")}

# Optional additional tools, e.g., modifyDBInstance, rebootDBInstance, describeEngineVersions, etc.

def main():
    """Main entry point for RDS MCP Server."""
    print(">>> RDS MCP Server starting up...", flush=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    app.run()

if __name__ == '__main__':
    main()
