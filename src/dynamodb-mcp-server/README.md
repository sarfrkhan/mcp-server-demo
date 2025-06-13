# AWS DynamoDB MCP Server

MCP Server for interacting with AWS DynamoDB

## Available MCP Tools

### Table Operations
- `create_table` - Creates a new DynamoDB table with optional secondary indexes
- `delete_table` - Deletes a table and all of its items
- `describe_table` - Returns table information including status, creation time, key schema and indexes
- `list_tables` - Returns a paginated list of table names in your account
- `update_table` - Modifies table settings including provisioned throughput, global secondary indexes, and DynamoDB Streams configuration

### Item Operations
- `get_item` - Returns attributes for an item with the given primary key
- `put_item` - Creates a new item or replaces an existing item in a table
- `update_item` - Edits an existing item's attributes, or adds a new item if it does not already exist
- `delete_item` - Deletes a single item in a table by primary key

### Query and Scan Operations
- `query` - Returns items from a table or index matching a partition key value, with optional sort key filtering
- `scan` - Returns items and attributes by scanning a table or secondary index

### Backup and Recovery
- `create_backup` - Creates a backup of a DynamoDB table
- `describe_backup` - Describes an existing backup of a table
- `list_backups` - Returns a list of table backups
- `restore_table_from_backup` - Creates a new table from a backup
- `describe_continuous_backups` - Returns continuous backup and point in time recovery status
- `update_continuous_backups` - Enables or disables point in time recovery

### Time to Live (TTL)
- `update_time_to_live` - Enables or disables Time to Live (TTL) for the specified table
- `describe_time_to_live` - Returns the Time to Live (TTL) settings for a table

### Export Operations
- `describe_export` - Returns information about a table export
- `list_exports` - Returns a list of table exports

### Tags and Resource Policies
- `put_resource_policy` - Attaches a resource-based policy document to a table or stream
- `get_resource_policy` - Returns the resource-based policy document attached to a table or stream
- `tag_resource` - Adds tags to a DynamoDB resource
- `untag_resource` - Removes tags from a DynamoDB resource
- `list_tags_of_resource` - Returns tags for a DynamoDB resource

### Misc
- `describe_limits` - Returns the current provisioned-capacity quotas for your AWS account
- `describe_endpoints` - Returns DynamoDB endpoints for the current region
