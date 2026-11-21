"""
app/graph/state.py - Typed graph state schema for LangGraph workflow.
"""

from typing import TypedDict, Optional, List, Dict, Any


class GraphState(TypedDict, total=False):
    question: str
    schema_context: Dict[str, Any]
    sql: Optional[str]
    validation: Optional[Dict[str, Any]]
    execution_result: Optional[Dict[str, Any]]
    error: Optional[str]
    retry_count: int
    clarification: Optional[str]
    approval_granted: Optional[bool]
    explanation: Optional[Dict[str, Any]]
    final_status: str  # "success" | "blocked" | "failed" | "needs_input"
    skip_explainer: Optional[bool]
    trace: List[Dict[str, Any]]
