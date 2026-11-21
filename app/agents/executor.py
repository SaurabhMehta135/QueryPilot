"""
app/agents/executor.py - Query Execution Agent.
Deterministic agent that executes read-only SQL queries through the MCP database client.
"""

from typing import Dict, Any, Optional
from app.mcp_client.client import MCPDatabaseClient


class QueryExecutor:
    """Executes read-only SQL queries over MCP protocol."""

    def __init__(self, mcp_client: Optional[MCPDatabaseClient] = None):
        self.mcp = mcp_client or MCPDatabaseClient()

    async def execute(self, sql: str) -> Dict[str, Any]:
        """Calls run_readonly_query on the MCP database server."""
        return await self.mcp.run_readonly_query(sql)
