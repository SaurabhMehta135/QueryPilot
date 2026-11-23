"""
app/mcp_server/server.py - Standalone MCP Database Server for QueryPilot.
Provides four read-only database tools over stdio transport.
Enforces read-only connection URI, progress-handler timeout, row caps, and masking.
"""

import os
import sys
import time
import sqlite3
from typing import List, Dict, Any, Optional

from mcp.server.fastmcp import FastMCP
from app.config import settings
from app.guardrails.masking import mask_rows

mcp = FastMCP("querypilot-database-server")


def get_db_path() -> str:
    """Returns absolute path to SQLite database."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base_dir, settings.DATABASE_PATH)
    return os.path.abspath(path).replace("\\", "/")


ALLOWED_AUTHORIZER_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_PRAGMA,
    sqlite3.SQLITE_RECURSIVE,
}
DISALLOWED_AUTHORIZER_FUNCTIONS = {
    "load_extension",
    "writefile",
    "readfile",
    "edit",
    "system",
    "eval",
}
ALLOWED_AUTHORIZER_PRAGMAS = {
    "table_info",
    "foreign_key_list",
}


def readonly_authorizer(action: int, arg1: Optional[str], arg2: Optional[str], dbname: Optional[str], source: Optional[str]) -> int:
    """
    Allow-list SQLite Authorizer:
    Permits strictly read-only execution primitives (SELECT, READ, safe FUNCTIONs, schema metadata PRAGMAs).
    Denies everything else by default: ATTACH, DETACH, VACUUM, CREATE TEMP TABLE, load_extension, and all DDL/DML.
    """
    if action not in ALLOWED_AUTHORIZER_ACTIONS:
        return sqlite3.SQLITE_DENY

    if action == sqlite3.SQLITE_FUNCTION:
        if arg2 and arg2.lower() in DISALLOWED_AUTHORIZER_FUNCTIONS:
            return sqlite3.SQLITE_DENY

    if action == sqlite3.SQLITE_PRAGMA:
        if arg1 and arg1.lower() not in ALLOWED_AUTHORIZER_PRAGMAS:
            return sqlite3.SQLITE_DENY

    return sqlite3.SQLITE_OK


def get_readonly_connection(timeout_seconds: Optional[float] = None) -> sqlite3.Connection:
    """Opens a strictly read-only SQLite connection at the database level."""
    db_path = get_db_path()
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.set_authorizer(readonly_authorizer)

    timeout = timeout_seconds or settings.QUERY_TIMEOUT_SECONDS
    start_time = time.perf_counter()

    def timeout_progress_handler():
        if time.perf_counter() - start_time > timeout:
            return 1  # Non-zero interrupts the query
        return 0

    conn.set_progress_handler(timeout_progress_handler, 1000)
    return conn


@mcp.tool()
def list_tables() -> List[str]:
    """Returns a list of all user table names in the database, excluding internal tables."""
    conn = get_readonly_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = [row[0] for row in cur.fetchall()]
        return tables
    finally:
        conn.close()


@mcp.tool()
def describe_table(table_name: str) -> Dict[str, Any]:
    """
    Returns column details (name, type, notnull, pk) and foreign keys for a table.
    Rejects unknown or internal table names.
    """
    conn = get_readonly_connection()
    try:
        cur = conn.cursor()
        # Verify table exists to prevent injection/invalid access
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name=?
        """, (table_name,))
        if not cur.fetchone():
            return {
                "error": True,
                "error_type": "NoSuchTableError",
                "message": f"Table '{table_name}' does not exist.",
            }

        cur.execute(f"PRAGMA table_info('{table_name}')")
        raw_cols = cur.fetchall()
        columns = [
            {
                "cid": row[0],
                "name": row[1],
                "type": row[2],
                "notnull": bool(row[3]),
                "default_value": row[4],
                "pk": bool(row[5]),
            }
            for row in raw_cols
        ]

        cur.execute(f"PRAGMA foreign_key_list('{table_name}')")
        raw_fks = cur.fetchall()
        foreign_keys = [
            {
                "id": row[0],
                "seq": row[1],
                "table": row[2],
                "from": row[3],
                "to": row[4],
                "on_update": row[5],
                "on_delete": row[6],
            }
            for row in raw_fks
        ]

        return {
            "table_name": table_name,
            "columns": columns,
            "foreign_keys": foreign_keys,
            "error": None,
        }
    finally:
        conn.close()


@mcp.tool()
def sample_rows(table_name: str, n: int = 5, unmasked: bool = False) -> Dict[str, Any]:
    """
    Returns up to 5 sample rows for a table with masking applied to sensitive fields,
    unless unmasked=True is explicitly specified (e.g. for evaluation ground-truth verification).
    Hard-capped at max 5 rows.
    """
    capped_n = max(1, min(int(n), 5))
    conn = get_readonly_connection()
    try:
        cur = conn.cursor()
        # Validate table exists
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name=?
        """, (table_name,))
        if not cur.fetchone():
            return {
                "error": True,
                "error_type": "NoSuchTableError",
                "message": f"Table '{table_name}' does not exist.",
            }

        cur.execute(f"SELECT * FROM '{table_name}' LIMIT ?", (capped_n,))
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchall()]

        if settings.ENABLE_MASKING and not unmasked:
            rows = mask_rows(cols, rows, settings.SENSITIVE_COLUMNS)

        return {
            "table_name": table_name,
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "error": None,
        }
    finally:
        conn.close()


@mcp.tool()
def run_readonly_query(sql: str, unmasked: bool = False) -> Dict[str, Any]:
    """
    Executes a read-only SQL query on the database.
    Enforces progress-handler timeout, hard row cap, and read-only URI security.
    Applies masking unless unmasked=True is passed for eval verification.
    """
    conn = get_readonly_connection(timeout_seconds=settings.QUERY_TIMEOUT_SECONDS)
    start_time = time.perf_counter()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        duration_ms = (time.perf_counter() - start_time) * 1000

        cols = [d[0] for d in cur.description] if cur.description else []
        row_cap = settings.MAX_ROW_CAP

        # Fetch up to cap + 1 to detect truncation
        fetched = cur.fetchmany(row_cap + 1)
        truncated = len(fetched) > row_cap
        rows = [list(r) for r in fetched[:row_cap]]

        if settings.ENABLE_MASKING and not unmasked:
            rows = mask_rows(cols, rows, settings.SENSITIVE_COLUMNS)

        return {
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "duration_ms": round(duration_ms, 2),
            "error": None,
        }
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        err_msg = str(e)
        if "interrupted" in err_msg.lower():
            err_type = "ExecutionTimeout"
            err_detail = f"Query timed out after {settings.QUERY_TIMEOUT_SECONDS}s."
        elif "readonly" in err_msg.lower() or "not authorized" in err_msg.lower():
            err_type = "ReadOnlyViolation"
            err_detail = "Write or unauthorized operation rejected: database connection is read-only."
        else:
            err_type = type(e).__name__
            err_detail = err_msg

        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "duration_ms": round(duration_ms, 2),
            "error": {
                "error_type": err_type,
                "message": err_detail,
            },
        }
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "duration_ms": round(duration_ms, 2),
            "error": {
                "error_type": type(e).__name__,
                "message": str(e),
            },
        }
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
