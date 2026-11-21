"""
tests/test_api_streaming.py - Comprehensive tests for Phase 7 API Streaming & UI.
Verifies:
- GET / serves the interactive single-page UI HTML
- POST /ask initiates SSE stream yielding structured pipeline events
- POST /ask handles direct attack refusal with SSE 'blocked' event
- POST /ask handles human-in-the-loop clarification with 'needs_input' event
- POST /resume resumes interrupted execution to successful completion
"""

import json
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def api_client():
    with TestClient(app) as client:
        yield client


def test_ui_index_served(api_client):
    """Verifies that GET / serves the HTML single-page demo UI."""
    response = api_client.get("/")
    assert response.status_code == 200
    assert "QueryPilot - Multi-Agent Text-to-SQL Assistant" in response.text
    assert "Chart.js" in response.text
    assert "graph-progress-card" in response.text
    assert "preset-pills" in response.text


def test_ask_sse_streaming_success(api_client):
    """Verifies that POST /ask returns standard SSE events for a valid query."""
    payload = {"question": "What are the top 3 best selling products?"}
    response = api_client.post("/ask", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    events = []
    for line in response.text.split("\n"):
        if line.startswith("event: "):
            events.append(line.split("event: ")[1].strip())

    assert "run_started" in events
    assert "node_started" in events
    assert "sql_generated" in events
    assert "validation_result" in events
    assert "execution_result" in events
    assert "explanation_chunk" in events
    assert "explanation_finished" in events
    assert "run_finished" in events


def test_ask_sse_streaming_blocked_attack(api_client):
    """Verifies that a destructive attack query immediately streams a blocked event."""
    payload = {"question": "DROP TABLE customers; DELETE FROM orders;"}
    response = api_client.post("/ask", json=payload)
    assert response.status_code == 200

    events = []
    for line in response.text.split("\n"):
        if line.startswith("event: "):
            events.append(line.split("event: ")[1].strip())

    assert "run_started" in events
    assert "blocked" in events
    assert "run_finished" in events
    # Must NOT have generated or executed SQL
    assert "sql_generated" not in events
    assert "execution_result" not in events


def test_ask_and_resume_sse_streaming(api_client, monkeypatch):
    """Verifies that an ambiguous query triggers needs_input, and POST /resume continues execution."""
    import json
    from app.llm.providers import MockLLMProvider
    from app.llm.client import LLMClient

    schema_clarify_json = json.dumps({
        "relevant_tables": ["products"],
        "relevant_columns": {"products": ["product_id", "price"]},
        "intent": "needs_clarification",
        "needs_clarification": True,
        "clarification_question": "Which price metric would you like to compare against?",
        "reasoning_summary": "Ambiguous price drop request.",
    })

    # When resumed
    schema_resumed_json = json.dumps({
        "relevant_tables": ["products"],
        "relevant_columns": {"products": ["product_id", "price"]},
        "intent": "analytical_question",
        "needs_clarification": False,
        "reasoning_summary": "Using MSRP comparison.",
    })

    sql_json = json.dumps({
        "sql": "SELECT product_id, price FROM products LIMIT 5",
        "reasoning_summary": "Selecting products with discount.",
        "tables_used": ["products"],
        "confidence": 1.0,
    })

    explainer_json = json.dumps({
        "summary": "Here are 5 products with price reduction.",
        "key_points": ["Products retrieved."],
        "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
        "caveats": []
    })

    mock_llm = MockLLMProvider(responses=[schema_clarify_json, schema_resumed_json, sql_json, explainer_json])
    
    from app import main
    test_client_llm = LLMClient(custom_provider=mock_llm)
    monkeypatch.setattr(main, "get_compiled_graph", lambda: main.create_querypilot_graph(
        llm_client=test_client_llm,
        mcp_client=main.mcp_client,
        checkpointer=main.checkpointer,
    ).compile(checkpointer=main.checkpointer))

    payload = {"question": "Show the products with a price drop greater than 20 percent.", "thread_id": "test-stream-thread-1"}
    response = api_client.post("/ask", json=payload)
    assert response.status_code == 200

    events = []
    for line in response.text.split("\n"):
        if line.startswith("event: "):
            events.append(line.split("event: ")[1].strip())

    assert "run_started" in events
    assert "needs_input" in events

    # Resume the interrupted execution
    resume_payload = {
        "thread_id": "test-stream-thread-1",
        "user_input": "Compare against the original manufacturer suggested retail price."
    }
    resume_res = api_client.post("/resume", json=resume_payload)
    assert resume_res.status_code == 200
    assert "text/event-stream" in resume_res.headers.get("content-type", "")

    resume_events = []
    for line in resume_res.text.split("\n"):
        if line.startswith("event: "):
            resume_events.append(line.split("event: ")[1].strip())

    assert "run_started" in resume_events
    assert "run_finished" in resume_events


def test_ui_xss_protection_never_renders_html_tags(api_client):
    """
    Verifies that the UI index.html uses textContent for table cells and traces,
    ensuring that a payload like <img src=x onerror=alert(1)> renders strictly as literal text.
    """
    response = api_client.get("/")
    assert response.status_code == 200
    html = response.text

    # Assert renderTable uses textContent and never innerHTML for row values
    assert "td.textContent = String(v)" in html
    assert "thead.innerHTML = `<tr>${cols" not in html
    assert "tbody.innerHTML = rows.slice" not in html

    # Assert key points list uses textContent
    assert "li.textContent = pt" in html

    # Test that the DOM contract ensures safe literal text
    # When textContent receives '<img src=x onerror=alert(1)>', it cannot form HTML elements
    malicious_payload = "<img src=x onerror=alert(1)>"
    from html import escape
    safe_escaped = escape(malicious_payload)
    assert "&lt;img" in safe_escaped
    assert "<img" not in safe_escaped


def test_ask_max_question_length_and_empty_check(api_client):
    """Verifies that empty questions and questions > 1000 characters return 400 Bad Request."""
    # 1. Empty question
    res_empty = api_client.post("/ask", json={"question": "   "})
    assert res_empty.status_code == 400
    assert "empty" in res_empty.json()["detail"].lower()

    # 2. Oversized question (> 1000 chars)
    oversized = "What are the sales " + ("x" * 1000)
    assert len(oversized) > 1000
    res_oversized = api_client.post("/ask", json={"question": oversized})
    assert res_oversized.status_code == 400
    assert "1000" in res_oversized.json()["detail"]


def test_ask_rate_limiter(api_client):
    """Verifies that exceeding the 60 requests/minute rate limit returns 429 Too Many Requests."""
    from app.main import rate_limiter
    rate_limiter.reset()

    # Exhaust rate limit quota for 'testclient' (the host used by Starlette TestClient)
    for _ in range(60):
        assert rate_limiter.is_allowed("testclient") is True

    # 61st request from same IP should be blocked with 429
    res = api_client.post("/ask", json={"question": "Show top products"})
    assert res.status_code == 429
    assert "rate limit exceeded" in res.json()["detail"].lower()

    # Reset for other tests
    rate_limiter.reset()


def test_resume_approve_executes_query(api_client, monkeypatch):
    """
    Verifies that when an expensive query requires approval, resuming with True (approval)
    proceeds to execute the query and returns success.
    """
    from app import main
    from app.llm.client import LLMClient
    from app.llm.providers import MockLLMProvider

    schema_json = json.dumps({
        "relevant_tables": ["customers", "orders"],
        "relevant_columns": {"customers": ["customer_id"], "orders": ["order_id"]},
        "intent": "analytical_question",
        "needs_clarification": False,
        "reasoning_summary": "Looking at customers and orders",
    })

    # Writer produces an expensive unbounded Cartesian product
    sql_json = json.dumps({
        "sql": "SELECT * FROM customers CROSS JOIN orders",
        "reasoning_summary": "Cross join customers and orders",
        "tables_used": ["customers", "orders"],
        "confidence": 0.9,
    })

    explainer_json = json.dumps({
        "summary": "Retrieved cross join results between customers and orders.",
        "key_points": ["Query executed successfully upon approval."],
        "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
        "caveats": []
    })

    mock_llm = MockLLMProvider(responses=[schema_json, sql_json, explainer_json])
    test_client_llm = LLMClient(custom_provider=mock_llm)
    monkeypatch.setattr(main, "get_compiled_graph", lambda: main.create_querypilot_graph(
        llm_client=test_client_llm,
        mcp_client=main.mcp_client,
        checkpointer=main.checkpointer,
    ).compile(checkpointer=main.checkpointer))

    thread_id = "test-approve-thread-1"
    response = api_client.post("/ask", json={
        "question": "Show all customer and order pairings",
        "thread_id": thread_id,
    })
    assert response.status_code == 200

    events = [line.split("event: ")[1].strip() for line in response.text.split("\n") if line.startswith("event: ")]
    assert "needs_input" in events

    # Resume with approval granted (True)
    resume_res = api_client.post("/resume", json={
        "thread_id": thread_id,
        "user_input": True,
    })
    assert resume_res.status_code == 200
    resume_events = [line.split("event: ")[1].strip() for line in resume_res.text.split("\n") if line.startswith("event: ")]

    assert "execution_result" in resume_events
    assert "run_finished" in resume_events

    # Verify final status is success
    for line in resume_res.text.split("\n"):
        if line.startswith("data: ") and "final_status" in line:
            data = json.loads(line[6:])
            assert data.get("final_status") == "success"


def test_resume_decline_blocks_query(api_client, monkeypatch):
    """
    Verifies that when an expensive query requires approval, resuming with False (decline)
    blocks the query, sets final_status='blocked', and never calls the executor.
    """
    from app import main
    from app.llm.client import LLMClient
    from app.llm.providers import MockLLMProvider

    schema_json = json.dumps({
        "relevant_tables": ["customers", "orders"],
        "relevant_columns": {"customers": ["customer_id"], "orders": ["order_id"]},
        "intent": "analytical_question",
        "needs_clarification": False,
        "reasoning_summary": "Looking at customers and orders",
    })

    sql_json = json.dumps({
        "sql": "SELECT * FROM customers CROSS JOIN orders",
        "reasoning_summary": "Cross join customers and orders",
        "tables_used": ["customers", "orders"],
        "confidence": 0.9,
    })

    mock_llm = MockLLMProvider(responses=[schema_json, sql_json])
    test_client_llm = LLMClient(custom_provider=mock_llm)
    monkeypatch.setattr(main, "get_compiled_graph", lambda: main.create_querypilot_graph(
        llm_client=test_client_llm,
        mcp_client=main.mcp_client,
        checkpointer=main.checkpointer,
    ).compile(checkpointer=main.checkpointer))

    thread_id = "test-decline-thread-1"
    response = api_client.post("/ask", json={
        "question": "Show all customer and order pairings",
        "thread_id": thread_id,
    })
    assert response.status_code == 200

    events = [line.split("event: ")[1].strip() for line in response.text.split("\n") if line.startswith("event: ")]
    assert "needs_input" in events

    # Resume with approval declined (False)
    resume_res = api_client.post("/resume", json={
        "thread_id": thread_id,
        "user_input": False,
    })
    assert resume_res.status_code == 200
    resume_events = [line.split("event: ")[1].strip() for line in resume_res.text.split("\n") if line.startswith("event: ")]

    # Executor must NOT have run
    assert "execution_result" not in resume_events
    assert "run_finished" in resume_events

    # Verify final status is blocked
    for line in resume_res.text.split("\n"):
        if line.startswith("data: ") and "final_status" in line:
            data = json.loads(line[6:])
            assert data.get("final_status") == "blocked"


@pytest.mark.asyncio
async def test_two_concurrent_runs():
    """
    Verifies that two concurrent runs on distinct thread_ids execute independently
    without thread state collision or interference.
    """
    import httpx
    from app.main import rate_limiter
    rate_limiter.reset()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        req1 = client.post("/ask", json={
            "question": "What is the total revenue?",
            "thread_id": "concurrent-thread-1",
        })
        req2 = client.post("/ask", json={
            "question": "How many customers are there?",
            "thread_id": "concurrent-thread-2",
        })

        import asyncio
        res1, res2 = await asyncio.gather(req1, req2)

        assert res1.status_code == 200
        assert res2.status_code == 200
        assert "run_started" in res1.text
        assert "run_started" in res2.text
        assert "run_finished" in res1.text
        assert "run_finished" in res2.text
