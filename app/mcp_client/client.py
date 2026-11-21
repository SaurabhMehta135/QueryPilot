"""
app/mcp_client/client.py - MCP Database Client used by agents to communicate with
the standalone MCP database server over stdio transport.
Agents never open the database directly; all access is mediated through this client.
"""

import os
import sys
import json
from typing import List, Dict, Any, Optional
from contextlib import AsyncExitStack

from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client
from app.config import settings


class MCPDatabaseClient:
    """Client for the standalone QueryPilot MCP database server."""

    def __init__(self, server_path: Optional[str] = None, env: Optional[Dict[str, str]] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.repo_root = base_dir
        self.server_path = server_path or os.path.join(base_dir, "app", "mcp_server", "server.py")
        self.custom_env = env or {}
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None

    def _get_server_params(self) -> StdioServerParameters:
        env = os.environ.copy()
        env["PYTHONPATH"] = self.repo_root
        env.update(self.custom_env)
        return StdioServerParameters(
            command=sys.executable,
            args=[self.server_path],
            env=env,
        )

    async def connect(self):
        """Initializes and opens persistent stdio session with MCP server."""
        if self._session is None:
            self._exit_stack = AsyncExitStack()
            params = self._get_server_params()
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
            session = await self._exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._session = session
        return self

    async def aclose(self):
        """Closes the active stdio session and terminates the server subprocess."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._session = None

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Executes a tool on the MCP server, managing session if not already in context."""
        if self._session is None:
            await self.connect()
        res = await self._session.call_tool(tool_name, arguments)
        return self._parse_tool_response(res)

    def _parse_tool_response(self, response: Any) -> Any:
        """Parses MCP content items into Python native structures."""
        if not response.content:
            return None

        # If list of multiple text blocks (e.g. list_tables)
        if len(response.content) > 1:
            return [block.text for block in response.content]

        text = response.content[0].text
        # Try JSON parsing
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    async def list_tables(self) -> List[str]:
        """Calls list_tables on the MCP database server."""
        res = await self.call_tool("list_tables", {})
        if isinstance(res, list):
            return res
        if isinstance(res, str):
            return [res]
        return []

    async def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Calls describe_table on the MCP database server."""
        return await self.call_tool("describe_table", {"table_name": table_name})

    async def sample_rows(self, table_name: str, n: int = 5, unmasked: bool = False) -> Dict[str, Any]:
        """Calls sample_rows on the MCP database server."""
        return await self.call_tool("sample_rows", {"table_name": table_name, "n": n, "unmasked": unmasked})

    async def run_readonly_query(self, sql: str, unmasked: bool = False) -> Dict[str, Any]:
        """Calls run_readonly_query on the MCP database server."""
        return await self.call_tool("run_readonly_query", {"sql": sql, "unmasked": unmasked})


class DirectMCPClient(MCPDatabaseClient):
    """
    High-performance in-process MCP client for test suites and evaluation harnesses.
    Executes identical MCP database tools directly without stdio subprocess overhead,
    enforcing the same read-only connection, timeouts, row caps, and masking rules.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        from app.mcp_server import server
        func = getattr(server, tool_name, None)
        if func is None:
            raise ValueError(f"Unknown MCP tool: {tool_name}")
        return func(**arguments)

    async def list_tables(self) -> List[str]:
        from app.mcp_server.server import list_tables
        return list_tables()

    async def describe_table(self, table_name: str) -> Dict[str, Any]:
        from app.mcp_server.server import describe_table
        return describe_table(table_name)

    async def sample_rows(self, table_name: str, n: int = 5, unmasked: bool = False) -> Dict[str, Any]:
        from app.mcp_server.server import sample_rows
        return sample_rows(table_name, n=n, unmasked=unmasked)

    async def run_readonly_query(self, sql: str, unmasked: bool = False) -> Dict[str, Any]:
        from app.mcp_server.server import run_readonly_query
        return run_readonly_query(sql=sql, unmasked=unmasked)
