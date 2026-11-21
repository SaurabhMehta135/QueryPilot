"""
tests/test_linear_graph.py - End-to-end verification of the linear LangGraph pipeline.
Tests all agents and asserts successful execution from user question to explanation.
"""

import json
import pytest
from app.graph.builder import create_linear_graph
from app.graph.state import GraphState
from app.llm.client import LLMClient
from app.llm.providers import MockLLMProvider
from app.mcp_client.client import MCPDatabaseClient, DirectMCPClient


@pytest.mark.asyncio
async def test_linear_graph_happy_path():
    """
    Acceptance test for Phase 3:
    Runs a happy-path question through the 4-node pipeline and verifies that
    a valid SQL query is generated, executed on the database via MCP,
    and explained with structured insights and chart suggestions.
    """
    # Program realistic responses for the three LLM agents in sequence:
    # 1. SchemaAgent response
    schema_mock = json.dumps({
        "relevant_tables": ["products", "order_items"],
        "relevant_columns": {
            "products": ["product_id", "name", "price"],
            "order_items": ["product_id", "quantity"]
        },
        "needs_clarification": False,
        "clarification_question": None,
        "reasoning_summary": "Need products for names and order_items to sum quantities sold."
    })

    # 2. SQLWriterAgent response
    sql_mock = json.dumps({
        "sql": "SELECT p.name, SUM(oi.quantity) AS total_sold FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_id, p.name ORDER BY total_sold DESC LIMIT 3",
        "reasoning_summary": "Joined products and order_items, summed quantity, ordered descending with limit 3.",
        "tables_used": ["products", "order_items"],
        "confidence": 0.98
    })

    # 3. ExplainerAgent response
    explainer_mock = json.dumps({
        "summary": "The top 3 best-selling products by quantity are Ultra Wireless Headphones, Pro Gaming Mechanical Keyboard, and 4K Ultra HD Action Camera.",
        "key_points": [
            "Ultra Wireless Headphones is the highest volume seller.",
            "Gaming keyboards maintained strong consistent volume across orders.",
            "Action cameras ranked third in total units sold."
        ],
        "chart": {
            "chart_type": "bar",
            "x": "name",
            "y": "total_sold",
            "title": "Top 3 Products by Units Sold"
        },
        "caveats": ["Includes completed orders."]
    })

    mock_llm = MockLLMProvider(responses=[schema_mock, sql_mock, explainer_mock])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()

    builder = create_linear_graph(llm_client=llm_client, mcp_client=mcp_client)
    app = builder.compile()

    initial_state: GraphState = {
        "question": "What are our top 3 best-selling products by quantity?",
        "retry_count": 0,
        "trace": [],
    }

    final_state = await app.ainvoke(initial_state)

    # Acceptance assertions:
    assert final_state["final_status"] == "success"
    assert "SELECT p.name" in final_state["sql"]
    assert final_state["schema_context"]["relevant_tables"] == ["products", "order_items"]

    # Verify actual database execution occurred via MCP
    exec_res = final_state["execution_result"]
    assert exec_res is not None
    assert exec_res["error"] is None
    assert exec_res["columns"] == ["name", "total_sold"]
    assert len(exec_res["rows"]) == 3
    assert exec_res["rows"][0][1] > 0

    # Verify explanation and chart recommendation
    explanation = final_state["explanation"]
    assert explanation is not None
    assert "Ultra Wireless Headphones" in explanation["summary"]
    assert len(explanation["key_points"]) == 3
    assert explanation["chart"]["chart_type"] == "bar"
    assert explanation["chart"]["x"] == "name"

    # Verify observability trace
    traces = final_state["trace"]
    assert len(traces) == 4
    nodes = [t["node"] for t in traces]
    assert nodes == ["schema_agent", "sql_writer", "executor", "explainer"]
    for t in traces:
        assert t["duration_ms"] >= 0
