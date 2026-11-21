"""
app/graph/routing.py - Conditional edge routing functions for LangGraph workflow.
Controls rewrite loops, error repair loops, human-in-the-loop branching, and retry cap termination.
"""

from typing import Literal
from app.graph.state import GraphState
from app.config import settings


def route_after_schema(state: GraphState) -> Literal["clarification_node", "writer_node", "failure_node"]:
    """
    Routes from schema_node:
    - If intent is destructive_request or off_topic -> failure_node (direct block/refusal)
    - If needs_clarification and not yet clarified -> clarification_node
    - Otherwise -> writer_node
    """
    schema_ctx = state.get("schema_context", {})
    intent = schema_ctx.get("intent", "analytical_question")

    if intent in ("destructive_request", "off_topic"):
        return "failure_node"

    needs_clarification = schema_ctx.get("needs_clarification", False) or (intent == "needs_clarification")
    has_clarification = bool(state.get("clarification"))

    if needs_clarification and not has_clarification:
        return "clarification_node"
    return "writer_node"


def route_after_validator(state: GraphState) -> Literal["approval_node", "executor_node", "writer_node", "failure_node"]:
    """
    Routes from validator:
    - If unsafe and retries remain -> writer_node
    - If unsafe and retries exhausted -> failure_node
    - If safe and expensive -> approval_node
    - If safe and normal -> executor_node
    """
    validation = state.get("validation", {})
    is_safe = validation.get("is_safe", False)
    retry_count = state.get("retry_count", 0)

    if not is_safe:
        if retry_count >= settings.MAX_RETRIES:
            return "failure_node"
        return "writer_node"

    # Safe
    if validation.get("is_expensive") and not state.get("approval_granted"):
        return "approval_node"

    return "executor_node"


def route_after_approval(state: GraphState) -> Literal["executor_node", "failure_node"]:
    """Routes to executor if approved, else to failure_node."""
    if state.get("approval_granted"):
        return "executor_node"
    return "failure_node"


def route_after_executor(state: GraphState) -> Literal["explainer_node", "writer_node", "failure_node", "__end__"]:
    """
    Routes from executor:
    - If execution succeeded and skip_explainer is set -> __end__
    - If execution succeeded and explainer needed -> explainer_node
    - If execution failed and retries remain -> writer_node (repair loop)
    - If execution failed and retries exhausted -> failure_node
    """
    exec_res = state.get("execution_result", {})
    has_error = bool(exec_res.get("error"))
    retry_count = state.get("retry_count", 0)

    if not has_error:
        if state.get("skip_explainer"):
            return "__end__"
        return "explainer_node"

    # Error repair loop
    if retry_count >= settings.MAX_RETRIES:
        return "failure_node"
    return "writer_node"
