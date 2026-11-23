"""
tests/test_eval_scoring_and_features.py - Tests for Run 4 scoring rules and features:
1. compare_results_strict: column-order-insensitive, numeric tolerance.
2. compare_results_lenient: column-order-insensitive, extra columns allowed, numeric tolerance.
3. Low-cardinality value discovery: excludes sensitive columns (email, phone), escapes planted injections.
4. skip_explainer graph execution mode: verifies execution stops at executor without running explainer.
"""

import pytest
import asyncio
from typing import List, Tuple
from unittest.mock import AsyncMock, patch

from evals.runner import compare_results_strict, compare_results_lenient
from app.agents.schema_agent import SchemaAgent
from app.graph.builder import create_querypilot_graph
from app.graph.state import GraphState
from app.llm.client import LLMClient
from app.mcp_client.client import DirectMCPClient


# =============================================================================
# 1. SCORING FUNCTION TESTS (Strict & Lenient)
# =============================================================================

def test_compare_results_strict_column_order_insensitivity():
    """Verifies that strict matching passes when columns are in different orders."""
    ref_rows = [
        ("Alice", 100.0, 5),
        ("Bob", 250.5, 3),
    ]
    # Generated has columns in order: (order_count, customer_name, total_spend)
    gen_rows_permuted = [
        (5, "Alice", 100.0),
        (3, "Bob", 250.5),
    ]
    assert compare_results_strict(gen_rows_permuted, ref_rows) is True


def test_compare_results_strict_numeric_tolerance():
    """Verifies that float rounding and numeric representations match within tolerance."""
    ref_rows = [
        ("Widget A", 19.99),
        ("Widget B", 5.0),
    ]
    gen_rows_tolerance = [
        ("Widget A", 19.991),  # rounds to 19.99
        ("Widget B", 5),       # int 5 matches float 5.0
    ]
    assert compare_results_strict(gen_rows_tolerance, ref_rows) is True


def test_compare_results_strict_rejects_extra_columns():
    """Strict matching must reject queries that return extra projection columns."""
    ref_rows = [
        ("Widget A",),
        ("Widget B",),
    ]
    gen_rows_extra = [
        ("Widget A", 19.99),
        ("Widget B", 29.99),
    ]
    assert compare_results_strict(gen_rows_extra, ref_rows) is False


def test_compare_results_lenient_allows_extra_columns():
    """Lenient matching must pass when generated query includes extra columns."""
    ref_rows = [
        ("Alice", 500.0),
        ("Bob", 300.0),
    ]
    # Generated query projects (customer_id, customer_name, extra_date, total_spent)
    gen_rows_extra_and_permuted = [
        (1, "Alice", "2024-01-01", 500.0),
        (2, "Bob", "2024-02-01", 300.0),
    ]
    assert compare_results_lenient(gen_rows_extra_and_permuted, ref_rows) is True


def test_compare_results_lenient_rejects_missing_columns():
    """Lenient matching must fail if generated query has fewer columns than reference."""
    ref_rows = [
        ("Alice", 500.0, 5),
    ]
    gen_rows_too_few = [
        ("Alice", 500.0),
    ]
    assert compare_results_lenient(gen_rows_too_few, ref_rows) is False


def test_compare_results_order_matters_flag():
    """Verifies that order_matters=True enforces exact row sequence for both strict and lenient."""
    ref_rows = [(1,), (2,), (3,)]
    gen_rows = [(3,), (1,), (2,)]

    # Strict: When order does not matter: multiset equality holds
    assert compare_results_strict(gen_rows, ref_rows, order_matters=False) is True
    # Strict: When order matters: sequence must be identical
    assert compare_results_strict(gen_rows, ref_rows, order_matters=True) is False

    # Lenient: When order does not matter: multiset equality holds
    assert compare_results_lenient(gen_rows, ref_rows, order_matters=False) is True
    # Lenient: When order matters: sequence must be identical
    assert compare_results_lenient(gen_rows, ref_rows, order_matters=True) is False

    # Lenient with extra column: respects order_matters
    gen_rows_extra = [(3, "extra3"), (1, "extra1"), (2, "extra2")]
    assert compare_results_lenient(gen_rows_extra, ref_rows, order_matters=False) is True
    assert compare_results_lenient(gen_rows_extra, ref_rows, order_matters=True) is False


def test_scoring_parameters_are_keyword_only():
    """Regression test: verifies that order_matters, gen_cols, ref_cols cannot be passed positionally."""
    ref_rows = [(1,)]
    gen_rows = [(1,)]

    with pytest.raises(TypeError):
        compare_results_strict(gen_rows, ref_rows, False)  # type: ignore

    with pytest.raises(TypeError):
        compare_results_lenient(gen_rows, ref_rows, False)  # type: ignore


# =============================================================================
# 2. LOW-CARDINALITY VALUE DISCOVERY & SECURITY TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_low_cardinality_excludes_sensitive_columns():
    """Verifies that low-cardinality value discovery strictly excludes email and phone."""
    schema_agent = SchemaAgent(llm_client=LLMClient(provider="mock"), mcp_client=DirectMCPClient())
    low_card = await schema_agent.get_low_cardinality_values(["customers", "payments", "orders"])

    # Ensure customers.email and customers.phone are NEVER included
    for full_col in low_card.keys():
        col_lower = full_col.lower()
        assert "email" not in col_lower, f"Sensitive column {full_col} leaked in low-cardinality values!"
        assert "phone" not in col_lower, f"Sensitive column {full_col} leaked in low-cardinality values!"

    # Verify legitimate categorical columns are captured
    assert any("status" in col or "state" in col or "method" in col for col in low_card.keys())


@pytest.mark.asyncio
async def test_low_cardinality_escapes_planted_injection():
    """
    Security Test: Verifies that if an attacker plants prompt injection delimiters
    or tags in a database categorical value, get_low_cardinality_values escapes them.
    """
    mock_mcp = AsyncMock()
    mock_mcp.describe_table.return_value = {
        "columns": [
            {"name": "status", "type": "TEXT", "pk": 0},
        ],
        "foreign_keys": [],
    }
    # Mock database returning a malicious prompt injection inside a categorical column
    mock_mcp.run_readonly_query.return_value = {
        "rows": [
            ("DROP/*<tag>*/TABLE",),
            ("normal_status",),
            ("<script>alert(1)</script>",),
        ],
        "columns": ["status"],
    }

    schema_agent = SchemaAgent(llm_client=LLMClient(provider="mock"), mcp_client=mock_mcp)
    low_card = await schema_agent.get_low_cardinality_values(["test_table"])

    vals = low_card.get("test_table.status", [])
    assert len(vals) == 3

    # Verify tags are neutralized / escaped
    for v in vals:
        assert "<" not in v, f"Raw unescaped delimiter '<' found in {v}"
        assert ">" not in v, f"Raw unescaped delimiter '>' found in {v}"
    assert any("&lt;" in v or "&gt;" in v for v in vals)


# =============================================================================
# 3. SKIP_EXPLAINER GRAPH EXECUTION MODE
# =============================================================================

@pytest.mark.asyncio
async def test_skip_explainer_terminates_at_executor():
    """
    Verifies that setting skip_explainer=True routes directly to __end__
    after query execution, skipping the Explainer agent entirely.
    """
    llm = LLMClient(provider="mock")
    mcp = DirectMCPClient()
    app = create_querypilot_graph(llm_client=llm, mcp_client=mcp).compile()

    state: GraphState = {
        "question": "How many products exist?",
        "retry_count": 0,
        "trace": [],
        "skip_explainer": True,
    }

    final_state = await app.ainvoke(state)

    # Status must be success
    assert final_state.get("final_status") == "success"

    # Explanation must NOT be generated
    assert final_state.get("explanation") is None

    # Trace must contain schema_agent and sql_writer, but NOT explainer
    nodes_in_trace = [s.get("node") for s in final_state.get("trace", []) if isinstance(s, dict)]
    assert "explainer" not in nodes_in_trace
    assert "schema_agent" in nodes_in_trace
    assert "sql_writer" in nodes_in_trace
