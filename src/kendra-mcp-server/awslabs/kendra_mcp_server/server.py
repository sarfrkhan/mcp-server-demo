import os
from typing import Any, Dict, Optional

from awslabs.kendra_mcp_server.common import get_kendra_client, handle_exceptions
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name='awslabs.kendra-mcp-server',
    instructions=(
        "Use these tools to list Amazon Kendra indexes and query them. "
        "When querying, the user may supply an indexId or rely on KENDRA_INDEX_ID env var."
    ),
    version='1.0.0',
)

@mcp.tool(name='KendraListIndexesTool')
@handle_exceptions
async def kendra_list_indexes_tool(
    region: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List all Amazon Kendra indexes in the specified region (or AWS_REGION if not provided).
    Returns dict with region, count, and indexes list.
    """
    # Determine region
    aws_region = region or os.environ.get('AWS_REGION', 'us-east-1')
    client = get_kendra_client(aws_region)
    indexes = []
    # Initial list_indices call
    response = client.list_indices()
    items = response.get('IndexConfigurationSummaryItems', [])
    for index in items:
        idx = {
            'id': index.get('Id'),
            'name': index.get('Name'),
            'status': index.get('Status'),
            'created_at': index.get('CreatedAt').isoformat() if index.get('CreatedAt') else None,
            'updated_at': index.get('UpdatedAt').isoformat() if index.get('UpdatedAt') else None,
            'edition': index.get('Edition'),
        }
        indexes.append(idx)
    # Pagination
    next_token = response.get('NextToken')
    while next_token:
        response = client.list_indices(NextToken=next_token)
        for index in response.get('IndexConfigurationSummaryItems', []):
            idx = {
                'id': index.get('Id'),
                'name': index.get('Name'),
                'status': index.get('Status'),
                'created_at': index.get('CreatedAt').isoformat() if index.get('CreatedAt') else None,
                'updated_at': index.get('UpdatedAt').isoformat() if index.get('UpdatedAt') else None,
                'edition': index.get('Edition'),
            }
            indexes.append(idx)
        next_token = response.get('NextToken')
    return {
        'region': aws_region,
        'count': len(indexes),
        'indexes': indexes,
    }

@mcp.tool(name='KendraQueryTool')
@handle_exceptions
async def kendra_query_tool(
    query: str,
    region: Optional[str] = None,
    indexId: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query Amazon Kendra index. Returns dict with query, total_results_count, and results list.
    Requires either indexId param or KENDRA_INDEX_ID env var.
    """
    aws_region = region or os.environ.get('AWS_REGION', 'us-east-1')
    client = get_kendra_client(aws_region)
    kendra_index_id = indexId or os.environ.get('KENDRA_INDEX_ID')
    if not kendra_index_id:
        raise ValueError('KENDRA_INDEX_ID environment variable is not set and no indexId provided.')
    response = client.query(IndexId=kendra_index_id, QueryText=query)
    results = {
        'query': query,
        'index_id': kendra_index_id,
        'total_results_count': response.get('TotalNumberOfResults', 0),
        'results': [],
    }
    for item in response.get('ResultItems', []):
        result_item: Dict[str, Any] = {
            'id': item.get('Id'),
            'type': item.get('Type'),
            'document_title': item.get('DocumentTitle', {}).get('Text', ''),
            'document_uri': item.get('DocumentURI', ''),
            'score': item.get('ScoreAttributes', {}).get('ScoreConfidence', ''),
        }
        if 'DocumentExcerpt' in item and 'Text' in item['DocumentExcerpt']:
            result_item['excerpt'] = item['DocumentExcerpt']['Text']
        if 'AdditionalAttributes' in item:
            result_item['additional_attributes'] = item['AdditionalAttributes']
        results['results'].append(result_item)
    return results

def main():
    """Entry point for the MCP server."""
    mcp.run()

if __name__ == '__main__':
    main()
