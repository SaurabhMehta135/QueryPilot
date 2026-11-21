"""
tests/test_observability.py - Comprehensive tests for Phase 6 Observability.
Verifies:
- Configurable model price table and cost estimation (app/observability/pricing.py)
- Local SQLite trace store persistence, query, and pagination (app/observability/store.py)
- Tracer aggregation of model_latency_ms, retry_wait_ms, and guardrail events (app/observability/tracer.py)
- FastAPI endpoints for /health, /schema, /traces, and /traces/{run_id} (app/main.py)
"""

import os
import uuid
import pytest
from fastapi.testclient import TestClient

from app.observability.pricing import estimate_cost, MODEL_PRICING
from app.observability.store import TraceStore
from app.observability.tracer import QueryPilotTracer
from app.main import app


# =====================================================================
# 1. PRICING & COST ESTIMATION TESTS
# =====================================================================

def test_pricing_calculation_gemini():
    """Verifies cost calculation for Gemini 3.1 Flash Lite."""
    # 10,000 prompt tokens ($0.075/1M) = $0.00075
    # 2,000 completion tokens ($0.30/1M) = $0.00060
    # Total = $0.00135
    cost = estimate_cost("gemini-3.1-flash-lite", prompt_tokens=10000, completion_tokens=2000)
    assert cost["is_estimate"] is True
    assert cost["prompt_tokens"] == 10000
    assert cost["completion_tokens"] == 2000
    assert cost["total_tokens"] == 12000
    assert cost["estimated_cost_usd"] == 0.00135
    assert cost["prompt_cost_usd"] == 0.00075
    assert cost["completion_cost_usd"] == 0.0006


def test_pricing_fallback_and_default():
    """Verifies fallback pricing for unknown models."""
    cost = estimate_cost("unknown-future-model", prompt_tokens=1000, completion_tokens=500)
    assert cost["is_estimate"] is True
    assert cost["estimated_cost_usd"] > 0


def test_pricing_mock_zero():
    """Verifies mock model cost is zero."""
    cost = estimate_cost("mock-model", prompt_tokens=5000, completion_tokens=5000)
    assert cost["estimated_cost_usd"] == 0.0


# =====================================================================
# 2. TRACE STORE PERSISTENCE & RETRIEVAL TESTS
# =====================================================================

def test_trace_store_save_and_retrieve(tmp_path):
    """Verifies persisting a trace and retrieving it by run_id."""
    db_file = str(tmp_path / "test_traces.db")
    store = TraceStore(db_path=db_file)

    run_id = str(uuid.uuid4())
    raw_trace = [
        {
            "node": "schema_agent",
            "model": "gemini-3.1-flash-lite",
            "provider": "gemini",
            "prompt_tokens": 1200,
            "completion_tokens": 80,
            "total_tokens": 1280,
            "duration_ms": 1500.0,
            "model_latency_ms": 1400.0,
            "retry_wait_ms": 100.0,
            "retry_attempts": 1,
            "output_summary": "Selected products table.",
        },
        {
            "node": "guardrails",
            "type": "guardrail_event",
            "action": "injection_wrapper_applied",
            "reason": "Escaped delimiters",
        },
        {
            "node": "sql_writer",
            "model": "gemini-3.1-flash-lite",
            "provider": "gemini",
            "prompt_tokens": 800,
            "completion_tokens": 50,
            "total_tokens": 850,
            "duration_ms": 1200.0,
            "model_latency_ms": 1200.0,
            "retry_wait_ms": 0.0,
            "retry_attempts": 0,
            "output_summary": "SELECT * FROM products LIMIT 5",
        },
        {
            "node": "guardrails",
            "type": "guardrail_event",
            "action": "masking_applied",
            "reason": "Masked emails",
        },
    ]

    saved = store.save_run(
        run_id=run_id,
        question="Show 5 products",
        final_status="success",
        sql="SELECT * FROM products LIMIT 5",
        trace=raw_trace,
        explanation={"summary": "Here are 5 products."},
        retry_count=0,
    )

    assert saved["run_id"] == run_id
    assert saved["total_tokens"] == 1280 + 850
    assert saved["model_latency_ms"] == 2600.0
    assert saved["retry_wait_ms"] == 100.0
    assert saved["estimated_cost_usd"] > 0
    assert len(saved["guardrail_events"]) == 2

    # Retrieve from DB
    retrieved = store.get_trace(run_id)
    assert retrieved is not None
    assert retrieved["run_id"] == run_id
    assert retrieved["question"] == "Show 5 products"
    assert retrieved["final_status"] == "success"
    assert retrieved["model_latency_ms"] == 2600.0
    assert retrieved["retry_wait_ms"] == 100.0
    assert len(retrieved["guardrail_events"]) == 2
    assert retrieved["explanation"]["summary"] == "Here are 5 products."


def test_trace_store_pagination(tmp_path):
    """Verifies listing traces with limit and offset."""
    db_file = str(tmp_path / "test_traces_pagination.db")
    store = TraceStore(db_path=db_file)

    for i in range(10):
        store.save_run(
            run_id=f"run-{i:02d}",
            question=f"Question {i}",
            final_status="success",
            sql=f"SELECT {i}",
            trace=[],
        )

    # First page
    page1 = store.list_traces(limit=4, offset=0)
    assert len(page1) == 4

    # Second page
    page2 = store.list_traces(limit=4, offset=4)
    assert len(page2) == 4
    assert page1[0]["run_id"] != page2[0]["run_id"]

    # Non-existent run
    assert store.get_trace("non-existent-id") is None


# =====================================================================
# 3. TRACER ORCHESTRATION TESTS
# =====================================================================

def test_tracer_record_and_query(tmp_path):
    """Verifies QueryPilotTracer saves and queries traces cleanly without crashing."""
    db_file = str(tmp_path / "tracer_test.db")
    store = TraceStore(db_path=db_file)
    tracer = QueryPilotTracer(store=store)

    run = tracer.record_run(
        question="How many categories exist?",
        final_status="success",
        sql="SELECT COUNT(*) FROM categories",
        trace=[
            {
                "node": "schema_agent",
                "model": "gemini-3.1-flash-lite",
                "prompt_tokens": 500,
                "completion_tokens": 50,
                "duration_ms": 800.0,
                "model_latency_ms": 800.0,
                "retry_wait_ms": 0.0,
            }
        ],
        explanation={"summary": "There are 7 categories."},
    )

    assert run["run_id"] is not None
    assert run["estimated_cost_usd"] > 0

    fetched = tracer.get_run(run["run_id"])
    assert fetched["question"] == "How many categories exist?"

    listed = tracer.list_runs(limit=10)
    assert len(listed) == 1
    assert listed[0]["run_id"] == run["run_id"]


# =====================================================================
# 3b. END-TO-END GRAPH PERSISTENCE & PRIVACY IN TRACES.DB
# =====================================================================

@pytest.mark.asyncio
async def test_graph_run_persists_complete_row_in_traces_db(tmp_path):
    """Verifies that an end-to-end graph run persists a fully populated row in traces.db."""
    import json
    import sqlite3
    from app.graph.builder import create_querypilot_graph
    from app.llm.client import LLMClient
    from app.llm.providers import MockLLMProvider
    from app.mcp_client.client import DirectMCPClient

    db_file = str(tmp_path / "graph_traces.db")
    store = TraceStore(db_path=db_file)
    tracer = QueryPilotTracer(store=store)

    schema_json = json.dumps({
        "relevant_tables": ["products"],
        "relevant_columns": {"products": ["product_id", "name"]},
        "intent": "analytical_question",
        "needs_clarification": False,
        "reasoning_summary": "Selecting products.",
    })
    sql_json = json.dumps({
        "sql": "SELECT product_id, name FROM products LIMIT 5",
        "reasoning_summary": "Returning 5 products.",
        "tables_used": ["products"],
        "confidence": 1.0,
    })
    explainer_json = json.dumps({
        "summary": "Here are 5 products from catalog.",
        "key_points": ["Products retrieved."],
        "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
        "caveats": []
    })

    mock_llm = MockLLMProvider(responses=[schema_json, sql_json, explainer_json])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()
    app = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client).compile()

    state = {"question": "List 5 products", "retry_count": 0, "trace": []}
    res = await app.ainvoke(state)

    # Persist via tracer
    run_record = tracer.record_run(
        question="List 5 products",
        final_status=res["final_status"],
        sql=res.get("sql"),
        trace=res["trace"],
        explanation=res.get("explanation"),
        retry_count=res.get("retry_count", 0),
    )

    run_id = run_record["run_id"]

    # Verify directly via raw SQLite connection to traces.db
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM traces WHERE run_id = ?", (run_id,))
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row["run_id"] == run_id
    assert row["question"] == "List 5 products"
    assert row["final_status"] == "success"
    assert "SELECT product_id, name FROM products" in row["sql"]
    assert row["total_tokens"] > 0
    assert row["total_latency_ms"] > 0
    assert row["model_latency_ms"] > 0
    assert row["estimated_cost_usd"] >= 0.0

    steps = json.loads(row["steps"])
    assert len(steps) >= 4  # schema, writer, validator, executor, explainer
    step_nodes = [s["node"] for s in steps]
    assert "schema_agent" in step_nodes
    assert "sql_writer" in step_nodes
    assert "safety_validator" in step_nodes
    assert "executor" in step_nodes

    guardrail_events = json.loads(row["guardrail_events"])
    assert len(guardrail_events) >= 1


@pytest.mark.asyncio
async def test_persisted_traces_contain_no_raw_emails(tmp_path):
    """
    Verifies that when customer emails are queried and the run trace is stored in traces.db,
    NO raw, unmasked email address appears anywhere in the persisted database row text.
    """
    import json
    import sqlite3
    from app.graph.builder import create_querypilot_graph
    from app.llm.client import LLMClient
    from app.llm.providers import MockLLMProvider
    from app.mcp_client.client import DirectMCPClient

    db_file = str(tmp_path / "privacy_traces.db")
    store = TraceStore(db_path=db_file)
    tracer = QueryPilotTracer(store=store)

    schema_json = json.dumps({
        "relevant_tables": ["customers"],
        "relevant_columns": {"customers": ["customer_id", "first_name", "email"]},
        "intent": "analytical_question",
        "needs_clarification": False,
        "reasoning_summary": "Selecting customer emails.",
    })
    sql_json = json.dumps({
        "sql": "SELECT customer_id, first_name, email FROM customers LIMIT 5",
        "reasoning_summary": "Returning customer contacts.",
        "tables_used": ["customers"],
        "confidence": 1.0,
    })
    explainer_json = json.dumps({
        "summary": "Here are 5 customers with emails: b***@testcorp.net, c***@example.com.",
        "key_points": ["Customer contacts retrieved."],
        "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
        "caveats": []
    })

    mock_llm = MockLLMProvider(responses=[schema_json, sql_json, explainer_json])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()
    app = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client).compile()

    state = {"question": "Show customer emails", "retry_count": 0, "trace": []}
    res = await app.ainvoke(state)

    # Persist via tracer
    run_record = tracer.record_run(
        question="Show customer emails",
        final_status=res["final_status"],
        sql=res.get("sql"),
        trace=res["trace"],
        explanation=res.get("explanation"),
        retry_count=res.get("retry_count", 0),
    )

    run_id = run_record["run_id"]

    # Read raw row from traces.db as string
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT * FROM traces WHERE run_id = ?", (run_id,))
    raw_row = cur.fetchone()
    conn.close()

    raw_row_text = json.dumps(list(raw_row))

    # Assert raw unmasked customer emails NEVER exist anywhere in the stored trace
    assert "john.smith@example.com" not in raw_row_text
    assert "sarah.jones@example.com" not in raw_row_text
    assert "betty.martinez@testcorp.net" not in raw_row_text
    assert "carol.white@example.com" not in raw_row_text

    # Masked representation must be present
    assert "***@" in raw_row_text


# =====================================================================
# 4. FASTAPI OBSERVABILITY ENDPOINTS TESTS
# =====================================================================

@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient wired to a temporary test trace database."""
    test_db = str(tmp_path / "api_traces.db")
    test_store = TraceStore(db_path=test_db)
    test_tracer = QueryPilotTracer(store=test_store)

    from app import main
    monkeypatch.setattr(main, "tracer", test_tracer)

    with TestClient(app) as test_client:
        yield test_client, test_tracer


def test_api_health(client):
    """Verifies /health endpoint returns healthy status and configuration."""
    test_client, _ = client
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "QueryPilot"
    assert "masking_enabled" in data


def test_api_schema(client):
    """Verifies /schema endpoint returns database tables and schema structures."""
    test_client, _ = client
    response = test_client.get("/schema")
    assert response.status_code == 200
    data = response.json()
    assert "tables" in data
    assert "schema" in data
    assert "categories" in data["tables"]
    assert "products" in data["tables"]


def test_api_traces_empty_and_populated(client):
    """Verifies /traces and /traces/{run_id} endpoints."""
    test_client, test_tracer = client

    # Empty list
    res = test_client.get("/traces")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["traces"] == []

    # 404 for unknown run_id
    res_404 = test_client.get("/traces/missing-uuid-123")
    assert res_404.status_code == 404

    # Seed one trace
    run_record = test_tracer.record_run(
        question="What is the average order total?",
        final_status="success",
        sql="SELECT AVG(total_amount) FROM orders",
        trace=[
            {
                "node": "schema_agent",
                "model": "gemini-3.1-flash-lite",
                "prompt_tokens": 1000,
                "completion_tokens": 100,
                "duration_ms": 1100.0,
                "model_latency_ms": 1100.0,
                "retry_wait_ms": 0.0,
            },
            {
                "node": "guardrails",
                "type": "guardrail_event",
                "action": "masking_applied",
                "reason": "Masked sensitive columns",
            },
        ],
        explanation={"summary": "Average order total is $342.15."},
    )
    run_id = run_record["run_id"]

    # Populated list
    res_pop = test_client.get("/traces?limit=10&offset=0")
    assert res_pop.status_code == 200
    pop_data = res_pop.json()
    assert pop_data["total"] == 1
    assert pop_data["traces"][0]["run_id"] == run_id
    assert pop_data["traces"][0]["model_latency_ms"] == 1100.0

    # Get by run_id
    res_single = test_client.get(f"/traces/{run_id}")
    assert res_single.status_code == 200
    single_data = res_single.json()
    assert single_data["run_id"] == run_id
    assert single_data["question"] == "What is the average order total?"
    assert single_data["final_status"] == "success"
    assert len(single_data["guardrail_events"]) == 1
    assert single_data["explanation"]["summary"] == "Average order total is $342.15."
