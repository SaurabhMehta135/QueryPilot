"""
tests/test_validator_and_graph.py - Comprehensive tests for Phase 4:
- All SQLValidator security rules, auto-LIMIT, and expensive query heuristics.
- Rewrite and error-repair loops.
- Termination proof: guaranteed halt at MAX_RETRIES.
- Human-in-the-loop interrupts and resumption via MemorySaver checkpointer.
"""

import json
import pytest
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from app.guardrails.sql_validator import SQLValidator
from app.graph.builder import create_querypilot_graph
from app.graph.state import GraphState
from app.llm.client import LLMClient
from app.llm.providers import MockLLMProvider
from app.mcp_client.client import MCPDatabaseClient, DirectMCPClient
from app.config import settings


# ==========================================
# 1. SQL VALIDATOR UNIT TESTS
# ==========================================

def test_validator_empty_and_unparseable():
    validator = SQLValidator()
    # Empty
    res = validator.validate_and_rewrite("")
    assert not res.is_safe
    assert "empty" in res.reason.lower()

    # Syntax error
    res2 = validator.validate_and_rewrite("SELECT ( FROM customers")
    assert not res2.is_safe
    assert "syntax error" in res2.reason.lower() or "unparseable" in res2.reason.lower()

    # Non-select statement
    res3 = validator.validate_and_rewrite("SELEC * FORM customers")
    assert not res3.is_safe
    assert "statement must be a select" in res3.reason.lower() or "syntax" in res3.reason.lower()


def test_validator_rejects_multi_statement():
    validator = SQLValidator()
    multi = "SELECT * FROM customers; DROP TABLE orders;"
    res = validator.validate_and_rewrite(multi)
    assert not res.is_safe
    assert "multi-statement" in res.reason.lower()


def test_validator_rejects_dml_ddl_and_pragma():
    validator = SQLValidator()
    attacks = [
        "DROP TABLE customers",
        "DELETE FROM orders",
        "UPDATE customers SET email = 'hacked@evil.com'",
        "INSERT INTO categories (name) VALUES ('Hacked')",
        "ALTER TABLE products ADD COLUMN secret TEXT",
        "CREATE TABLE backdoor (id INT)",
        "PRAGMA database_list",
    ]
    for sql in attacks:
        res = validator.validate_and_rewrite(sql)
        assert not res.is_safe, f"Failed to reject: {sql}"
        assert "prohibited" in res.reason.lower() or "statement must be a select" in res.reason.lower()


def test_validator_rejects_nested_prohibited_in_cte():
    validator = SQLValidator()
    cte_attack = "WITH evil AS (DELETE FROM customers) SELECT * FROM products"
    res = validator.validate_and_rewrite(cte_attack)
    assert not res.is_safe
    assert "prohibited" in res.reason.lower()


def test_validator_rejects_dangerous_functions():
    validator = SQLValidator()
    sql = "SELECT load_extension('malicious.so') FROM products"
    res = validator.validate_and_rewrite(sql)
    assert not res.is_safe
    assert "prohibited function" in res.reason.lower()


def test_validator_rejects_sqlite_master_and_internal():
    validator = SQLValidator()
    sql1 = "SELECT * FROM sqlite_master"
    res1 = validator.validate_and_rewrite(sql1)
    assert not res1.is_safe
    assert "internal schema table" in res1.reason.lower()

    sql2 = "SELECT * FROM sqlite_sequence"
    res2 = validator.validate_and_rewrite(sql2)
    assert not res2.is_safe
    assert "internal schema table" in res2.reason.lower()


def test_validator_rejects_unknown_tables():
    validator = SQLValidator(known_tables={"customers", "orders"})
    sql = "SELECT * FROM passwords"
    res = validator.validate_and_rewrite(sql)
    assert not res.is_safe
    assert "does not exist in schema" in res.reason.lower()


def test_validator_allows_valid_ctes():
    validator = SQLValidator()
    sql = "WITH high_spenders AS (SELECT customer_id FROM orders WHERE total_amount > 100) SELECT c.first_name FROM customers c JOIN high_spenders hs ON c.customer_id = hs.customer_id"
    res = validator.validate_and_rewrite(sql)
    assert res.is_safe
    assert res.rewritten_sql is not None


def test_validator_auto_limit():
    validator = SQLValidator(default_limit=50, max_limit_cap=200)

    # Injects limit when none is present
    res1 = validator.validate_and_rewrite("SELECT name, price FROM products")
    assert res1.is_safe
    assert "LIMIT 50" in res1.rewritten_sql

    # Clamps excessive limit
    res2 = validator.validate_and_rewrite("SELECT name, price FROM products LIMIT 10000")
    assert res2.is_safe
    assert "LIMIT 200" in res2.rewritten_sql

    # Preserves valid limit below cap
    res3 = validator.validate_and_rewrite("SELECT name, price FROM products LIMIT 10")
    assert res3.is_safe
    assert "LIMIT 10" in res3.rewritten_sql


def test_validator_expensive_query_flag():
    validator = SQLValidator()

    # Cartesian product (Cross Join / missing ON)
    expensive_sql = "SELECT * FROM customers CROSS JOIN orders"
    res = validator.validate_and_rewrite(expensive_sql)
    assert res.is_safe
    assert res.is_expensive is True

    # Standard query with proper join condition
    standard_sql = "SELECT c.first_name, o.total_amount FROM customers c JOIN orders o ON c.customer_id = o.customer_id"
    res2 = validator.validate_and_rewrite(standard_sql)
    assert res2.is_safe
    assert res2.is_expensive is False


# ==========================================
# 2. GRAPH LOOPS & TERMINATION GUARANTEE TESTS
# ==========================================

@pytest.mark.asyncio
async def test_graph_guaranteed_termination_at_max_retries():
    """
    CRITICAL ACCEPTANCE TEST:
    Proves that the graph cannot loop indefinitely.
    If the SQL writer produces queries that are repeatedly rejected by the validator,
    the graph strictly increments retry_count, halts at MAX_RETRIES,
    transitions to failure_node, and returns status 'blocked'.
    """
    schema_mock = json.dumps({
        "relevant_tables": ["customers"],
        "relevant_columns": {"customers": ["customer_id", "email"]},
        "needs_clarification": False,
        "clarification_question": None,
        "reasoning_summary": "Looking up customers."
    })

    # Writer repeatedly proposes prohibited DROP / DELETE queries
    unsafe_proposal = json.dumps({
        "sql": "DROP TABLE customers",
        "reasoning_summary": "Attempting drop.",
        "tables_used": ["customers"],
        "confidence": 0.5
    })

    mock_llm = MockLLMProvider(responses=[schema_mock, unsafe_proposal, unsafe_proposal, unsafe_proposal, unsafe_proposal])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()

    builder = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client)
    app = builder.compile()

    state: GraphState = {
        "question": "How many customers do we have?",
        "retry_count": 0,
        "trace": [],
    }

    final_state = await app.ainvoke(state)

    # Assert graph terminated gracefully
    assert final_state["final_status"] == "blocked"
    assert final_state["retry_count"] >= settings.MAX_RETRIES
    assert "halted (blocked)" in final_state["explanation"]["summary"]
    assert "Statement must be a SELECT" in final_state["error"] or "Prohibited" in final_state["error"]


@pytest.mark.asyncio
async def test_graph_error_repair_loop_success():
    """
    Verifies that a database execution error triggers the repair loop,
    and a subsequent corrected query succeeds end-to-end.
    """
    schema_mock = json.dumps({
        "relevant_tables": ["products"],
        "relevant_columns": {"products": ["product_id", "name"]},
        "needs_clarification": False,
        "clarification_question": None,
        "reasoning_summary": "Looking up products."
    })

    # Attempt 1: SQL with syntax error (invalid column)
    bad_sql = json.dumps({
        "sql": "SELECT non_existent_column FROM products",
        "reasoning_summary": "First try with invalid column.",
        "tables_used": ["products"],
        "confidence": 0.5
    })

    # Attempt 2: Repaired valid SQL
    good_sql = json.dumps({
        "sql": "SELECT name, price FROM products LIMIT 5",
        "reasoning_summary": "Fixed column reference.",
        "tables_used": ["products"],
        "confidence": 0.95
    })

    explainer_mock = json.dumps({
        "summary": "Here are 5 products from inventory.",
        "key_points": ["Products retrieved successfully."],
        "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
        "caveats": []
    })

    mock_llm = MockLLMProvider(responses=[schema_mock, bad_sql, good_sql, explainer_mock])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()

    builder = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client)
    app = builder.compile()

    state: GraphState = {
        "question": "Show me 5 products",
        "retry_count": 0,
        "trace": [],
    }

    final_state = await app.ainvoke(state)

    assert final_state["final_status"] == "success"
    assert final_state["retry_count"] == 1  # Retried exactly once
    assert "name" in final_state["sql"]
    assert len(final_state["execution_result"]["rows"]) > 0


# ==========================================
# 3. HUMAN-IN-THE-LOOP INTERRUPT & RESUME TESTS
# ==========================================

@pytest.mark.asyncio
async def test_human_in_the_loop_clarification():
    """Verifies that an ambiguous question interrupts for user clarification and resumes."""
    ambiguous_schema = json.dumps({
        "relevant_tables": [],
        "relevant_columns": {},
        "needs_clarification": True,
        "clarification_question": "Do you want product sales or customer lists?",
        "reasoning_summary": "Ambiguous input."
    })

    clarified_schema = json.dumps({
        "relevant_tables": ["products"],
        "relevant_columns": {"products": ["product_id", "name"]},
        "needs_clarification": False,
        "clarification_question": None,
        "reasoning_summary": "User clarified: products."
    })

    sql_mock = json.dumps({
        "sql": "SELECT name, price FROM products LIMIT 3",
        "reasoning_summary": "Selected 3 products.",
        "tables_used": ["products"],
        "confidence": 0.95
    })

    explainer_mock = json.dumps({
        "summary": "Displaying 3 products.",
        "key_points": ["Products retrieved."],
        "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
        "caveats": []
    })

    mock_llm = MockLLMProvider(responses=[ambiguous_schema, clarified_schema, sql_mock, explainer_mock])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()

    checkpointer = MemorySaver()
    builder = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client)
    app = builder.compile(checkpointer=checkpointer)

    thread_config = {"configurable": {"thread_id": "test_clarification_thread"}}

    # Initial invoke -> interrupts at clarification_node
    res1 = await app.ainvoke({
        "question": "Show me stuff",
        "retry_count": 0,
        "trace": [],
    }, config=thread_config)

    # Verify interrupt happened
    state_snapshot = app.get_state(thread_config)
    assert len(state_snapshot.tasks) > 0
    interrupts = state_snapshot.tasks[0].interrupts
    assert len(interrupts) > 0
    assert interrupts[0].value["type"] == "clarification_needed"
    assert "product sales or customer lists" in interrupts[0].value["question"]

    # Resume with clarification answer
    final_state = await app.ainvoke(
        Command(resume="I want product sales"),
        config=thread_config,
    )

    assert final_state["final_status"] == "success"
    assert final_state["clarification"] == "I want product sales"
    assert "products" in final_state["sql"]


@pytest.mark.asyncio
async def test_human_in_the_loop_expensive_approval():
    """Verifies that an expensive query interrupts for user approval and resumes on approval."""
    schema_mock = json.dumps({
        "relevant_tables": ["customers", "orders"],
        "relevant_columns": {"customers": ["customer_id"], "orders": ["order_id"]},
        "needs_clarification": False,
        "clarification_question": None,
        "reasoning_summary": "Cross joining."
    })

    expensive_sql = json.dumps({
        "sql": "SELECT * FROM customers CROSS JOIN orders",
        "reasoning_summary": "Cartesian product.",
        "tables_used": ["customers", "orders"],
        "confidence": 0.8
    })

    explainer_mock = json.dumps({
        "summary": "Completed approved query.",
        "key_points": ["Data loaded."],
        "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
        "caveats": []
    })

    mock_llm = MockLLMProvider(responses=[schema_mock, expensive_sql, explainer_mock])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()

    checkpointer = MemorySaver()
    builder = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client)
    app = builder.compile(checkpointer=checkpointer)

    thread_config = {"configurable": {"thread_id": "test_expensive_thread"}}

    # Initial invoke -> interrupts at approval_node
    res1 = await app.ainvoke({
        "question": "Run cross join",
        "retry_count": 0,
        "trace": [],
    }, config=thread_config)

    # Verify paused at approval_node
    snapshot = app.get_state(thread_config)
    assert len(snapshot.tasks) > 0
    interrupts = snapshot.tasks[0].interrupts
    assert len(interrupts) > 0
    assert interrupts[0].value["type"] == "approval_needed"

    # Resume with approval
    final_state = await app.ainvoke(Command(resume="yes"), config=thread_config)

    assert final_state["final_status"] == "success"
    assert final_state["approval_granted"] is True


@pytest.mark.asyncio
async def test_executor_never_called_when_approval_declined():
    """
    CHECK 3 TEST:
    Verifies that when a user declines approval for an expensive query,
    the graph routes directly to failure_node, executor_node is NEVER invoked,
    and no execution_result exists.
    """
    schema_mock = json.dumps({
        "relevant_tables": ["customers", "orders"],
        "relevant_columns": {"customers": ["customer_id"], "orders": ["order_id"]},
        "needs_clarification": False,
        "clarification_question": None,
        "reasoning_summary": "Cross joining."
    })

    expensive_sql = json.dumps({
        "sql": "SELECT * FROM customers CROSS JOIN orders",
        "reasoning_summary": "Cartesian product.",
        "tables_used": ["customers", "orders"],
        "confidence": 0.8
    })

    mock_llm = MockLLMProvider(responses=[schema_mock, expensive_sql])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()

    checkpointer = MemorySaver()
    builder = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client)
    app = builder.compile(checkpointer=checkpointer)

    thread_config = {"configurable": {"thread_id": "test_declined_thread"}}

    # Initial invoke -> interrupts
    await app.ainvoke({
        "question": "Run cross join",
        "retry_count": 0,
        "trace": [],
    }, config=thread_config)

    # Resume with decline ("no")
    final_state = await app.ainvoke(Command(resume="no"), config=thread_config)

    # Asserts
    assert final_state["final_status"] == "blocked"
    assert final_state.get("approval_granted") is False
    assert final_state.get("execution_result") is None
    # Confirm executor was never called in traces
    nodes_executed = [t["node"] for t in final_state.get("trace", [])]
    assert "executor" not in nodes_executed


@pytest.mark.asyncio
async def test_executor_runs_rewritten_sql():
    """
    CHECK 3 TEST:
    Verifies that the executor runs the validator's rewritten SQL (e.g. auto-injected LIMIT),
    rather than the un-rewritten proposal from the SQL writer.
    """
    schema_mock = json.dumps({
        "relevant_tables": ["products"],
        "relevant_columns": {"products": ["product_id", "name"]},
        "needs_clarification": False,
        "clarification_question": None,
        "reasoning_summary": "Products."
    })

    # Writer produces SQL without any LIMIT
    sql_without_limit = json.dumps({
        "sql": "SELECT name, price FROM products",
        "reasoning_summary": "No limit specified.",
        "tables_used": ["products"],
        "confidence": 0.95
    })

    explainer_mock = json.dumps({
        "summary": "Products listed.",
        "key_points": ["Found products."],
        "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
        "caveats": []
    })

    mock_llm = MockLLMProvider(responses=[schema_mock, sql_without_limit, explainer_mock])
    llm_client = LLMClient(custom_provider=mock_llm)
    mcp_client = DirectMCPClient()

    builder = create_querypilot_graph(llm_client=llm_client, mcp_client=mcp_client)
    app = builder.compile()

    final_state = await app.ainvoke({
        "question": "List products",
        "retry_count": 0,
        "trace": [],
    })

    assert final_state["final_status"] == "success"
    # Confirm final_state['sql'] has been rewritten with auto-LIMIT
    assert "LIMIT" in final_state["sql"]
    assert final_state["validation"]["rewritten_sql"] == final_state["sql"]
