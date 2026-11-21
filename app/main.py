"""
app/main.py - FastAPI application for QueryPilot.
Provides SSE streaming endpoints (/ask, /resume), schema inspection,
observability trace endpoints (/traces, /traces/{run_id}), and serves the interactive demo UI.
"""

import os
import re
import json
import uuid
import asyncio
from collections import defaultdict
import time
from typing import List, Dict, Any, Optional, Union, AsyncGenerator
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.config import settings
from app.graph.builder import create_querypilot_graph
from app.graph.state import GraphState
from app.llm.client import LLMClient
from app.mcp_client.client import DirectMCPClient
from app.observability.store import TraceStore
from app.observability.tracer import QueryPilotTracer

app = FastAPI(
    title="QueryPilot API",
    description="Multi-agent text-to-SQL assistant with LangGraph, MCP, deterministic guardrails, full observability, and SSE streaming.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core singletons
tracer = QueryPilotTracer()
mcp_client = DirectMCPClient()
checkpointer = MemorySaver()


class SimpleRateLimiter:
    """Sliding-window in-memory rate limiter per client IP."""
    def __init__(self, requests_per_minute: int = 60):
        self.rpm = requests_per_minute
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        window_start = now - 60.0
        self.requests[client_id] = [t for t in self.requests[client_id] if t > window_start]
        if len(self.requests[client_id]) >= self.rpm:
            return False
        self.requests[client_id].append(now)
        return True

    def reset(self):
        self.requests.clear()


rate_limiter = SimpleRateLimiter(requests_per_minute=60)


def get_compiled_graph():
    """Builds and compiles the QueryPilot LangGraph workflow with current settings and checkpointer."""
    return create_querypilot_graph(
        llm_client=LLMClient(),
        mcp_client=mcp_client,
        checkpointer=checkpointer,
    ).compile(checkpointer=checkpointer)


class AskRequest(BaseModel):
    question: str
    thread_id: Optional[str] = None


class ResumeRequest(BaseModel):
    thread_id: str
    user_input: Any


@app.get("/health")
def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "QueryPilot",
        "default_llm_provider": settings.DEFAULT_LLM_PROVIDER,
        "masking_enabled": settings.ENABLE_MASKING,
    }


@app.get("/schema")
async def get_schema() -> Dict[str, Any]:
    """Returns overview of available database tables and column definitions."""
    tables = await mcp_client.list_tables()
    schema_overview = {}
    for table in tables:
        details = await mcp_client.describe_table(table)
        schema_overview[table] = details
    return {
        "tables": tables,
        "schema": schema_overview,
    }


@app.get("/traces")
def list_traces(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Retrieves recent run traces ordered by timestamp descending."""
    traces = tracer.list_runs(limit=limit, offset=offset)
    return {
        "total": len(traces),
        "limit": limit,
        "offset": offset,
        "traces": traces,
    }


@app.get("/traces/{run_id}")
def get_trace(run_id: str) -> Dict[str, Any]:
    """Retrieves single run trace by run_id."""
    record = tracer.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Trace with run_id '{run_id}' not found.")
    return record


async def run_event_stream(
    initial_input: Any,
    thread_id: str,
    run_id: str,
    question: str,
) -> AsyncGenerator[Dict[str, str], None]:
    """
    Generator streaming LangGraph execution steps as standard SSE events.
    Handles token-by-token explanation streaming, interrupt prompts, and trace saving.
    """
    yield {
        "event": "run_started",
        "data": json.dumps({"run_id": run_id, "question": question, "thread_id": thread_id}),
    }

    config = {"configurable": {"thread_id": thread_id}}
    final_status = "in_progress"
    final_trace = []
    generated_sql = None
    explanation_data = None
    retry_count = 0

    try:
        graph = get_compiled_graph()
        async for chunk in graph.astream(
            initial_input,
            config=config,
            stream_mode="updates",
        ):
            for node_name, node_output in chunk.items():
                if node_name == "schema_node":
                    yield {"event": "node_started", "data": json.dumps({"node": "schema_node"})}
                    ctx = node_output.get("schema_context", {})
                    final_status = node_output.get("final_status", final_status)
                    final_trace = node_output.get("trace", final_trace)

                    if ctx.get("intent") in ("destructive_request", "off_topic"):
                        yield {"event": "blocked", "data": json.dumps({"reason": node_output.get("error", "Request blocked by safety policy.")})}
                    else:
                        yield {
                            "event": "node_finished",
                            "data": json.dumps({
                                "node": "schema_node",
                                "tables": ctx.get("relevant_tables", []),
                                "intent": ctx.get("intent"),
                            }),
                        }

                elif node_name == "writer_node":
                    yield {"event": "node_started", "data": json.dumps({"node": "writer_node"})}
                    generated_sql = node_output.get("sql")
                    final_trace = node_output.get("trace", final_trace)
                    yield {
                        "event": "sql_generated",
                        "data": json.dumps({"sql": generated_sql}),
                    }
                    yield {
                        "event": "node_finished",
                        "data": json.dumps({"node": "writer_node", "sql": generated_sql}),
                    }

                elif node_name == "validator_node":
                    yield {"event": "node_started", "data": json.dumps({"node": "validator_node"})}
                    val = node_output.get("validation", {})
                    final_status = node_output.get("final_status", final_status)
                    final_trace = node_output.get("trace", final_trace)
                    yield {
                        "event": "validation_result",
                        "data": json.dumps(val),
                    }
                    yield {
                        "event": "node_finished",
                        "data": json.dumps({
                            "node": "validator_node",
                            "is_safe": val.get("is_safe"),
                            "is_expensive": val.get("is_expensive"),
                        }),
                    }

                elif node_name == "executor_node":
                    yield {"event": "node_started", "data": json.dumps({"node": "executor_node"})}
                    exec_res = node_output.get("execution_result", {})
                    final_status = node_output.get("final_status", final_status)
                    final_trace = node_output.get("trace", final_trace)
                    yield {
                        "event": "execution_result",
                        "data": json.dumps(exec_res),
                    }
                    yield {
                        "event": "node_finished",
                        "data": json.dumps({"node": "executor_node", "row_count": exec_res.get("row_count", 0)}),
                    }

                elif node_name == "explainer_node":
                    yield {"event": "node_started", "data": json.dumps({"node": "explainer_node"})}
                    explanation_data = node_output.get("explanation", {})
                    final_status = node_output.get("final_status", "success")
                    final_trace = node_output.get("trace", final_trace)

                    # Stream explanation summary token by token
                    summary_text = explanation_data.get("summary", "")
                    tokens = re.findall(r"\S+|\s+", summary_text)
                    for token in tokens:
                        yield {
                            "event": "explanation_chunk",
                            "data": json.dumps({"chunk": token}),
                        }
                        await asyncio.sleep(0.01)

                    yield {
                        "event": "explanation_finished",
                        "data": json.dumps(explanation_data),
                    }
                    yield {
                        "event": "node_finished",
                        "data": json.dumps({"node": "explainer_node"}),
                    }

                elif node_name == "failure_node":
                    final_status = node_output.get("final_status", "failed")
                    fail_exp = node_output.get("explanation", {})
                    yield {
                        "event": "error" if final_status == "failed" else "blocked",
                        "data": json.dumps({"message": fail_exp.get("summary")}),
                    }

                elif node_name == "__interrupt__":
                    # LangGraph interrupt raised for human input
                    final_status = "needs_input"
                    interrupt_val = node_output[0].value if isinstance(node_output, (list, tuple)) else node_output
                    int_type = interrupt_val.get("type", "input_needed")

                    yield {
                        "event": "needs_input",
                        "data": json.dumps({
                            "type": int_type,
                            "prompt": interrupt_val.get("question") or interrupt_val.get("reason"),
                            "sql": interrupt_val.get("sql"),
                            "thread_id": thread_id,
                        }),
                    }

    except Exception as e:
        final_status = "failed"
        yield {
            "event": "error",
            "data": json.dumps({"message": f"Pipeline error: {str(e)}"}),
        }

    # Ensure terminal status is never in_progress or None
    if final_status == "in_progress":
        final_status = "success" if explanation_data else "failed"

    # Persist trace in local store
    record = tracer.record_run(
        question=question,
        final_status=final_status,
        sql=generated_sql,
        trace=final_trace,
        explanation=explanation_data,
        retry_count=retry_count,
        run_id=run_id,
    )

    yield {
        "event": "run_finished",
        "data": json.dumps({
            "final_status": final_status,
            "run_id": run_id,
            "estimated_cost_usd": record.get("estimated_cost_usd", 0.0),
            "total_latency_ms": record.get("total_latency_ms", 0.0),
            "trace": record.get("steps", []),
            "guardrail_events": record.get("guardrail_events", []),
        }),
    }


@app.post("/ask")
async def ask_endpoint(req: AskRequest, request: Request) -> EventSourceResponse:
    """
    Starts an asynchronous multi-agent run for the user question.
    Returns Server-Sent Events (SSE) streaming progress, SQL, results, and tokens.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded (max 60 requests/minute). Please wait before submitting more queries.",
        )

    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if len(req.question) > 1000:
        raise HTTPException(
            status_code=400,
            detail=f"Question exceeds maximum allowed length of 1000 characters (received {len(req.question)}).",
        )

    thread_id = req.thread_id or str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    initial_state: GraphState = {
        "question": req.question,
        "retry_count": 0,
        "trace": [],
        "final_status": "in_progress",
    }
    return EventSourceResponse(run_event_stream(initial_state, thread_id, run_id, req.question))


@app.post("/resume")
async def resume_endpoint(req: ResumeRequest) -> EventSourceResponse:
    """
    Resumes an interrupted run with user clarification or approval response.
    Returns subsequent Server-Sent Events (SSE).
    """
    run_id = str(uuid.uuid4())
    resume_cmd = Command(resume=req.user_input)
    return EventSourceResponse(
        run_event_stream(
            initial_input=resume_cmd,
            thread_id=req.thread_id,
            run_id=run_id,
            question="[Resumed execution]",
        )
    )


# Serve Static UI Files
ui_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")
os.makedirs(ui_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=ui_dir), name="static")


@app.get("/", response_class=FileResponse)
def index():
    """Serves the single-page interactive chat UI."""
    index_path = os.path.join(ui_dir, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>QueryPilot API is running. UI building...</h1>")
    return FileResponse(index_path)
