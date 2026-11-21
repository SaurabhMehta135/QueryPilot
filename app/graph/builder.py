"""
app/graph/builder.py - StateGraph construction for QueryPilot.
Constructs the complete multi-agent LangGraph workflow pipeline with validation,
rewrite/repair loops, retry caps, failure node, human-in-the-loop interrupts, and checkpointer.
"""

import time
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import GraphState
from app.graph.routing import (
    route_after_schema,
    route_after_validator,
    route_after_approval,
    route_after_executor,
)
from app.agents.schema_agent import SchemaAgent
from app.agents.sql_writer import SQLWriterAgent
from app.agents.executor import QueryExecutor
from app.agents.explainer import ExplainerAgent
from app.guardrails.sql_validator import SQLValidator
from app.llm.client import LLMClient
from app.mcp_client.client import MCPDatabaseClient
from app.config import settings


def create_linear_graph(
    llm_client: Optional[LLMClient] = None,
    mcp_client: Optional[MCPDatabaseClient] = None,
) -> StateGraph:
    """Builds a linear 4-node pipeline without loops for Phase 3 verification."""
    schema_agent = SchemaAgent(llm_client=llm_client, mcp_client=mcp_client)
    sql_writer = SQLWriterAgent(llm_client=llm_client)
    executor = QueryExecutor(mcp_client=mcp_client)
    explainer = ExplainerAgent(llm_client=llm_client)

    builder = StateGraph(GraphState)

    async def schema_node(state: GraphState) -> Dict[str, Any]:
        question = state["question"]
        res = await schema_agent.select_schema(question)
        trace_item = {
            "node": "schema_agent",
            "model": res.model,
            "provider": res.provider,
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "total_tokens": res.total_tokens,
            "duration_ms": res.duration_ms,
            "output_summary": res.data.reasoning_summary,
        }
        traces = list(state.get("trace", []))
        traces.append(trace_item)
        return {
            "schema_context": res.data.model_dump(),
            "trace": traces,
        }

    async def writer_node(state: GraphState) -> Dict[str, Any]:
        question = state["question"]
        schema_context = state["schema_context"]
        res = await sql_writer.write_sql(question, schema_context)
        trace_item = {
            "node": "sql_writer",
            "model": res.model,
            "provider": res.provider,
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "total_tokens": res.total_tokens,
            "duration_ms": res.duration_ms,
            "output_summary": f"Generated SQL: {res.data.sql}",
        }
        traces = list(state.get("trace", []))
        traces.append(trace_item)
        return {
            "sql": res.data.sql,
            "trace": traces,
        }

    async def executor_node(state: GraphState) -> Dict[str, Any]:
        sql = state.get("sql", "")
        exec_res = await executor.execute(sql)
        trace_item = {
            "node": "executor",
            "model": "mcp-server",
            "provider": "sqlite",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "duration_ms": exec_res.get("duration_ms", 0.0),
            "output_summary": f"Executed query. Row count: {exec_res.get('row_count', 0)}",
            "error": exec_res.get("error"),
        }
        traces = list(state.get("trace", []))
        traces.append(trace_item)
        return {
            "execution_result": exec_res,
            "trace": traces,
        }

    async def explainer_node(state: GraphState) -> Dict[str, Any]:
        question = state["question"]
        sql = state.get("sql", "")
        exec_res = state.get("execution_result", {})
        res = await explainer.explain(question, sql, exec_res)
        trace_item = {
            "node": "explainer",
            "model": res.model,
            "provider": res.provider,
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "total_tokens": res.total_tokens,
            "duration_ms": res.duration_ms,
            "output_summary": res.data.summary,
        }
        traces = list(state.get("trace", []))
        traces.append(trace_item)
        return {
            "explanation": res.data.model_dump(),
            "final_status": "success",
            "trace": traces,
        }

    builder.add_node("schema_node", schema_node)
    builder.add_node("writer_node", writer_node)
    builder.add_node("executor_node", executor_node)
    builder.add_node("explainer_node", explainer_node)

    builder.add_edge(START, "schema_node")
    builder.add_edge("schema_node", "writer_node")
    builder.add_edge("writer_node", "executor_node")
    builder.add_edge("executor_node", "explainer_node")
    builder.add_edge("explainer_node", END)

    return builder


def create_querypilot_graph(
    llm_client: Optional[LLMClient] = None,
    mcp_client: Optional[MCPDatabaseClient] = None,
    validator: Optional[SQLValidator] = None,
    checkpointer: Optional[Any] = None,
) -> StateGraph:
    """
    Builds the full production QueryPilot StateGraph:
    - Schema Agent with human-in-the-loop clarification interrupt
    - SQL Writer with self-correction retry feedback
    - Safety Validator with auto-LIMIT, expensive query detection & approval interrupt
    - MCP Executor with error feedback
    - Failure Node ensuring guaranteed termination at MAX_RETRIES
    - Explainer Agent with grounded summary & chart suggestions
    """
    schema_agent = SchemaAgent(llm_client=llm_client, mcp_client=mcp_client)
    sql_writer = SQLWriterAgent(llm_client=llm_client)
    sql_validator = validator or SQLValidator(
        default_limit=settings.DEFAULT_QUERY_LIMIT,
        max_limit_cap=settings.MAX_ROW_CAP,
    )
    executor = QueryExecutor(mcp_client=mcp_client)
    explainer = ExplainerAgent(llm_client=llm_client)

    builder = StateGraph(GraphState)

    # 1. Schema Node
    async def schema_node(state: GraphState) -> Dict[str, Any]:
        question = state["question"]
        clarification = state.get("clarification")
        res = await schema_agent.select_schema(question, clarification_context=clarification)

        trace_item = {
            "node": "schema_agent",
            "model": res.model,
            "provider": res.provider,
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "total_tokens": res.total_tokens,
            "duration_ms": res.duration_ms,
            "latency_ms": res.duration_ms,
            "model_latency_ms": getattr(res, "model_latency_ms", res.duration_ms),
            "retry_wait_ms": getattr(res, "retry_wait_ms", 0.0),
            "retry_attempts": getattr(res, "retry_attempts", 0),
            "fallback_used": getattr(res, "fallback_used", False),
            "output_summary": res.data.reasoning_summary,
        }
        traces = list(state.get("trace", []))
        traces.append(trace_item)

        # Log untrusted wrapper guardrail event
        traces.append({
            "node": "guardrails",
            "type": "guardrail_event",
            "action": "injection_wrapper_applied",
            "reason": "Encapsulated database schema in <untrusted_data> delimiters",
        })

        # Check for direct destructive or off-topic refusal
        if res.data.intent in ("destructive_request", "off_topic"):
            block_reason = res.data.block_reason or f"Request blocked due to prohibited intent: {res.data.intent}."
            traces.append({
                "node": "guardrails",
                "type": "guardrail_event",
                "action": "destructive_intent_block",
                "reason": block_reason,
            })
            return {
                "schema_context": res.data.model_dump(),
                "final_status": "blocked",
                "error": block_reason,
                "trace": traces,
            }

        schema_dump = res.data.model_dump()
        low_card_vals = await schema_agent.get_low_cardinality_values(res.data.relevant_tables)
        if low_card_vals:
            schema_dump["low_cardinality_values"] = low_card_vals

        return {
            "schema_context": schema_dump,
            "final_status": "needs_input" if res.data.needs_clarification else state.get("final_status", "in_progress"),
            "trace": traces,
        }

    # 1b. Clarification Node (Human-in-the-loop interrupt for ambiguity)
    def clarification_node(state: GraphState) -> Dict[str, Any]:
        schema_ctx = state.get("schema_context", {})
        clarification_prompt = schema_ctx.get(
            "clarification_question",
            "Could you please clarify your question?"
        )
        user_answer = interrupt({
            "type": "clarification_needed",
            "question": clarification_prompt,
        })
        return {
            "clarification": str(user_answer),
            "final_status": "in_progress",
        }

    # 2. SQL Writer Node
    async def writer_node(state: GraphState) -> Dict[str, Any]:
        question = state["question"]
        schema_context = state.get("schema_context", {})
        previous_sql = state.get("sql")
        error_message = state.get("error")

        res = await sql_writer.write_sql(
            question=question,
            schema_context=schema_context,
            previous_sql=previous_sql,
            error_message=error_message,
        )

        trace_item = {
            "node": "sql_writer",
            "model": res.model,
            "provider": res.provider,
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "total_tokens": res.total_tokens,
            "duration_ms": res.duration_ms,
            "latency_ms": res.duration_ms,
            "model_latency_ms": getattr(res, "model_latency_ms", res.duration_ms),
            "retry_wait_ms": getattr(res, "retry_wait_ms", 0.0),
            "retry_attempts": getattr(res, "retry_attempts", 0),
            "fallback_used": getattr(res, "fallback_used", False),
            "output_summary": f"Generated SQL: {res.data.sql}",
            "retry_index": state.get("retry_count", 0),
        }
        traces = list(state.get("trace", []))
        traces.append(trace_item)
        traces.append({
            "node": "guardrails",
            "type": "guardrail_event",
            "action": "injection_wrapper_applied",
            "reason": "Encapsulated schema and previous errors in <untrusted_data> delimiters",
        })

        return {
            "sql": res.data.sql,
            "trace": traces,
        }

    # 3. Validator Node
    def validator_node(state: GraphState) -> Dict[str, Any]:
        sql = state.get("sql", "")
        # Get schema allowed tables if available
        allowed = None
        schema_ctx = state.get("schema_context", {})
        if schema_ctx and "relevant_tables" in schema_ctx and schema_ctx["relevant_tables"]:
            allowed = set(schema_ctx["relevant_tables"])

        val_start = time.perf_counter()
        val_res = sql_validator.validate_and_rewrite(sql, allowed_tables=allowed)
        val_duration_ms = (time.perf_counter() - val_start) * 1000
        traces = list(state.get("trace", []))

        trace_item = {
            "node": "safety_validator",
            "model": "sqlglot-deterministic",
            "provider": "local",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "duration_ms": round(val_duration_ms, 2),
            "output_summary": f"Safe: {val_res.is_safe}, Expensive: {val_res.is_expensive}",
            "error": val_res.reason,
        }
        traces.append(trace_item)

        # Rejection case
        if not val_res.is_safe:
            traces.append({
                "node": "guardrails",
                "type": "guardrail_event",
                "action": "validator_rejection",
                "reason": val_res.reason,
            })
            new_retry_count = state.get("retry_count", 0) + 1
            final_status = "blocked" if new_retry_count >= settings.MAX_RETRIES else "retrying"
            return {
                "validation": val_res.model_dump(),
                "error": val_res.reason,
                "retry_count": new_retry_count,
                "final_status": final_status,
                "trace": traces,
            }

        # Safe and accepted
        # If expensive and not yet approved, status during approval interrupt is needs_input
        is_approval_needed = val_res.is_expensive and not state.get("approval_granted")
        final_status = "needs_input" if is_approval_needed else state.get("final_status", "in_progress")

        return {
            "validation": val_res.model_dump(),
            "sql": val_res.rewritten_sql,
            "final_status": final_status,
            "error": None,
            "trace": traces,
        }

    # 3b. Approval Node (Human-in-the-loop interrupt for expensive queries)
    def approval_node(state: GraphState) -> Dict[str, Any]:
        sql = state.get("sql", "")
        user_approval = interrupt({
            "type": "approval_needed",
            "reason": "Query contains an expensive Cartesian scan or unconstrained multi-table join.",
            "sql": sql,
        })
        approved = str(user_approval).lower() in ("true", "yes", "approved", "1")
        if not approved:
            traces = list(state.get("trace", []))
            traces.append({
                "node": "guardrails",
                "type": "guardrail_event",
                "action": "approval_declined",
                "reason": "Expensive query approval declined by user",
            })
            return {
                "approval_granted": False,
                "final_status": "blocked",
                "error": "Query execution cancelled: expensive query was not approved by user.",
                "trace": traces,
            }
        return {
            "approval_granted": True,
            "final_status": "in_progress",
            "error": None,
        }

    # 4. Executor Node
    async def executor_node(state: GraphState) -> Dict[str, Any]:
        sql = state.get("sql", "")
        exec_start = time.perf_counter()
        exec_res = await executor.execute(sql)
        node_duration_ms = (time.perf_counter() - exec_start) * 1000
        traces = list(state.get("trace", []))

        trace_item = {
            "node": "executor",
            "model": "mcp-server",
            "provider": "sqlite",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "duration_ms": round(node_duration_ms, 2),
            "engine_latency_ms": exec_res.get("duration_ms", 0.0),
            "output_summary": f"Executed query. Row count: {exec_res.get('row_count', 0)}",
            "error": exec_res.get("error"),
        }
        traces.append(trace_item)

        if settings.ENABLE_MASKING:
            traces.append({
                "node": "guardrails",
                "type": "guardrail_event",
                "action": "masking_applied",
                "reason": f"Masked sensitive columns in {exec_res.get('row_count', 0)} rows",
            })

        if exec_res.get("error"):
            new_retry_count = state.get("retry_count", 0) + 1
            final_status = "failed" if new_retry_count >= settings.MAX_RETRIES else "retrying"
            return {
                "execution_result": exec_res,
                "error": str(exec_res["error"]),
                "retry_count": new_retry_count,
                "final_status": final_status,
                "trace": traces,
            }

        return {
            "execution_result": exec_res,
            "final_status": "success" if state.get("skip_explainer") else state.get("final_status", "in_progress"),
            "error": None,
            "trace": traces,
        }

    # 5. Explainer Node
    async def explainer_node(state: GraphState) -> Dict[str, Any]:
        question = state["question"]
        sql = state.get("sql", "")
        exec_res = state.get("execution_result", {})
        res = await explainer.explain(question, sql, exec_res)

        trace_item = {
            "node": "explainer",
            "model": res.model,
            "provider": res.provider,
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "total_tokens": res.total_tokens,
            "duration_ms": res.duration_ms,
            "latency_ms": res.duration_ms,
            "model_latency_ms": getattr(res, "model_latency_ms", res.duration_ms),
            "retry_wait_ms": getattr(res, "retry_wait_ms", 0.0),
            "retry_attempts": getattr(res, "retry_attempts", 0),
            "fallback_used": getattr(res, "fallback_used", False),
            "output_summary": res.data.summary,
        }
        traces = list(state.get("trace", []))
        traces.append(trace_item)
        traces.append({
            "node": "guardrails",
            "type": "guardrail_event",
            "action": "injection_wrapper_applied",
            "reason": "Encapsulated query execution result rows in <untrusted_data> delimiters",
        })

        return {
            "explanation": res.data.model_dump(),
            "final_status": "success",
            "trace": traces,
        }

    # 6. Failure Node
    def failure_node(state: GraphState) -> Dict[str, Any]:
        status = state.get("final_status")
        if not status or status in ("retrying", "in_progress"):
            err_lower = (state.get("error") or "").lower()
            if "blocked" in err_lower or "prohibited" in err_lower:
                status = "blocked"
            else:
                status = "failed"
        reason = state.get("error") or "Maximum retries exceeded without achieving a safe, valid query."
        explanation = {
            "summary": f"Query execution halted ({status}): {reason}",
            "key_points": [
                f"Outcome: {status.upper()}",
                f"Diagnostic Reason: {reason}",
                f"Total Retries Attempted: {state.get('retry_count', 0)}",
            ],
            "chart": {
                "chart_type": "table_only",
                "x": None,
                "y": None,
                "title": None,
            },
            "caveats": ["Execution safely terminated to prevent unauthorized operations or runaway loops."],
        }
        return {
            "explanation": explanation,
            "final_status": status,
        }

    # Register nodes
    builder.add_node("schema_node", schema_node)
    builder.add_node("clarification_node", clarification_node)
    builder.add_node("writer_node", writer_node)
    builder.add_node("validator_node", validator_node)
    builder.add_node("approval_node", approval_node)
    builder.add_node("executor_node", executor_node)
    builder.add_node("explainer_node", explainer_node)
    builder.add_node("failure_node", failure_node)

    # Wire Edges
    builder.add_edge(START, "schema_node")

    # Conditional edge from schema_node
    builder.add_conditional_edges(
        "schema_node",
        route_after_schema,
        {
            "clarification_node": "clarification_node",
            "writer_node": "writer_node",
            "failure_node": "failure_node",
        },
    )

    # Edge from clarification back to schema_node
    builder.add_edge("clarification_node", "schema_node")

    builder.add_edge("writer_node", "validator_node")

    # Conditional edge from validator_node
    builder.add_conditional_edges(
        "validator_node",
        route_after_validator,
        {
            "executor_node": "executor_node",
            "writer_node": "writer_node",
            "approval_node": "approval_node",
            "failure_node": "failure_node",
        },
    )

    # Conditional edge from approval_node
    builder.add_conditional_edges(
        "approval_node",
        route_after_approval,
        {
            "executor_node": "executor_node",
            "failure_node": "failure_node",
        },
    )

    # Conditional edge from executor_node
    builder.add_conditional_edges(
        "executor_node",
        route_after_executor,
        {
            "explainer_node": "explainer_node",
            "writer_node": "writer_node",
            "failure_node": "failure_node",
            "__end__": END,
        },
    )

    builder.add_edge("explainer_node", END)
    builder.add_edge("failure_node", END)

    return builder
