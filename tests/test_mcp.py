"""
tests/test_mcp.py - Comprehensive tests for standalone MCP Database Server & Client.
Verifies all 4 tools, read-only connection enforcement, progress timeout, and row capping.
"""

import pytest
from app.mcp_client.client import MCPDatabaseClient, DirectMCPClient
from app.config import settings


@pytest.fixture
def mcp_client():
    return DirectMCPClient()


@pytest.mark.asyncio
async def test_mcp_list_tables(mcp_client):
    """Verifies list_tables returns all seeded tables and excludes internal SQLite tables."""
    async with mcp_client as client:
        tables = await client.list_tables()
        assert isinstance(tables, list)
        expected = {"categories", "products", "customers", "orders", "order_items", "payments", "reviews"}
        assert expected.issubset(set(tables))
        assert not any(t.startswith("sqlite_") for t in tables)


@pytest.mark.asyncio
async def test_mcp_describe_table(mcp_client):
    """Verifies describe_table returns structured columns and foreign keys, and rejects unknown tables."""
    async with mcp_client as client:
        # Valid table
        res = await client.describe_table("customers")
        assert res["table_name"] == "customers"
        assert res["error"] is None
        col_names = {c["name"] for c in res["columns"]}
        assert "customer_id" in col_names
        assert "email" in col_names
        assert "phone" in col_names

        # Foreign keys check
        orders_res = await client.describe_table("orders")
        assert len(orders_res["foreign_keys"]) >= 1
        fk = orders_res["foreign_keys"][0]
        assert fk["table"] == "customers"

        # Unknown table rejection
        invalid_res = await client.describe_table("non_existent_table")
        assert invalid_res.get("error") is True
        assert invalid_res.get("error_type") == "NoSuchTableError"


@pytest.mark.asyncio
async def test_mcp_sample_rows_and_masking(mcp_client):
    """Verifies sample_rows caps at 5 and applies sensitive column masking."""
    async with mcp_client as client:
        # Request 50 rows -> must be capped at 5
        res = await client.sample_rows("customers", n=50)
        assert res["error"] is None
        assert res["row_count"] <= 5
        assert len(res["rows"]) <= 5

        # Check masking on email and phone
        email_idx = res["columns"].index("email")
        phone_idx = res["columns"].index("phone")

        for row in res["rows"]:
            email_val = row[email_idx]
            phone_val = row[phone_idx]
            assert "@" in email_val
            assert "***" in email_val, f"Email was not masked: {email_val}"
            if phone_val is not None:
                assert "***" in phone_val, f"Phone was not masked: {phone_val}"


@pytest.mark.asyncio
async def test_mcp_run_readonly_query_success(mcp_client):
    """Verifies successful read-only query execution."""
    async with mcp_client as client:
        res = await client.run_readonly_query("SELECT count(*) as total_orders FROM orders")
        assert res["error"] is None
        assert res["columns"] == ["total_orders"]
        assert len(res["rows"]) == 1
        assert res["rows"][0][0] > 1000
        assert res["duration_ms"] > 0
        assert res["truncated"] is False


@pytest.mark.asyncio
async def test_mcp_readonly_connection_blocks_writes(mcp_client):
    """
    CRITICAL SECURITY TEST:
    Proves that even if destructive queries bypass the validator and reach the server,
    they fail at the SQLite connection layer due to mode=ro.
    """
    async with mcp_client as client:
        # DROP
        drop_res = await client.run_readonly_query("DROP TABLE customers")
        assert drop_res["error"] is not None
        assert drop_res["error"]["error_type"] == "ReadOnlyViolation"

        # INSERT
        insert_res = await client.run_readonly_query("INSERT INTO categories (name) VALUES ('Hacked')")
        assert insert_res["error"] is not None
        assert insert_res["error"]["error_type"] == "ReadOnlyViolation"

        # UPDATE
        update_res = await client.run_readonly_query("UPDATE customers SET email = 'pwned@test.com'")
        assert update_res["error"] is not None
        assert update_res["error"]["error_type"] == "ReadOnlyViolation"

        # DELETE
        delete_res = await client.run_readonly_query("DELETE FROM orders")
        assert delete_res["error"] is not None
        assert delete_res["error"]["error_type"] == "ReadOnlyViolation"


@pytest.mark.asyncio
async def test_mcp_query_timeout(monkeypatch):
    """Verifies that long-running/runaway queries trigger progress-handler timeout."""
    monkeypatch.setattr(settings, "QUERY_TIMEOUT_SECONDS", 0.3)
    client = DirectMCPClient()
    # Infinite recursive query
    runaway_sql = "WITH RECURSIVE r(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM r) SELECT count(*) FROM r"
    res = await client.run_readonly_query(runaway_sql)
    assert res["error"] is not None
    assert res["error"]["error_type"] == "ExecutionTimeout"


@pytest.mark.asyncio
async def test_mcp_row_cap(monkeypatch):
    """Verifies that queries exceeding MAX_ROW_CAP are truncated with truncated=True."""
    monkeypatch.setattr(settings, "MAX_ROW_CAP", 10)
    client = DirectMCPClient()
    res = await client.run_readonly_query("SELECT * FROM order_items")
    assert res["error"] is None
    assert res["row_count"] == 10
    assert len(res["rows"]) == 10
    assert res["truncated"] is True


@pytest.mark.real_stdio
@pytest.mark.asyncio
async def test_real_stdio_mcp_server_integration():
    """Single genuine stdio integration test verifying end-to-end process transport."""
    client = MCPDatabaseClient()
    async with client as c:
        tables = await c.list_tables()
        assert "products" in tables
