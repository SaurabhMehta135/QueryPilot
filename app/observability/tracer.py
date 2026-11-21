"""
app/observability/tracer.py - Run tracer orchestrator.
Coordinates local persistence via TraceStore and optional remote tracing via Langfuse.
"""

import uuid
from typing import Dict, Any, List, Optional
from app.config import settings
from app.observability.store import TraceStore
from app.observability.pricing import estimate_cost


class QueryPilotTracer:
    """Manages recording and querying execution traces for QueryPilot runs."""

    def __init__(self, store: Optional[TraceStore] = None):
        self.store = store or TraceStore()
        self.langfuse_client = None
        if settings.LANGFUSE_ENABLED and settings.LANGFUSE_PUBLIC_KEY:
            try:
                from langfuse import Langfuse
                self.langfuse_client = Langfuse(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    host=settings.LANGFUSE_HOST or "https://cloud.langfuse.com",
                )
            except Exception:
                self.langfuse_client = None

    def record_run(
        self,
        question: str,
        final_status: str,
        sql: Optional[str],
        trace: List[Dict[str, Any]],
        explanation: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records the complete run trace to local storage (traces.db) and optionally Langfuse.
        Returns the enriched trace record.
        """
        active_run_id = run_id or str(uuid.uuid4())
        record = self.store.save_run(
            run_id=active_run_id,
            question=question,
            final_status=final_status,
            sql=sql,
            trace=trace,
            explanation=explanation,
            retry_count=retry_count,
        )

        # Optional Langfuse export if enabled
        if self.langfuse_client:
            try:
                lf_trace = self.langfuse_client.trace(
                    id=active_run_id,
                    name="querypilot_run",
                    input={"question": question},
                    output={
                        "final_status": final_status,
                        "sql": sql,
                        "explanation": explanation,
                    },
                    metadata={
                        "retry_count": retry_count,
                        "total_latency_ms": record["total_latency_ms"],
                        "estimated_cost_usd": record["estimated_cost_usd"],
                    },
                )
                for step in record["steps"]:
                    lf_trace.generation(
                        name=step.get("node", "step"),
                        model=step.get("model"),
                        usage={
                            "input": step.get("prompt_tokens", 0),
                            "output": step.get("completion_tokens", 0),
                            "total": step.get("total_tokens", 0),
                        },
                        metadata={
                            "duration_ms": step.get("duration_ms"),
                            "model_latency_ms": step.get("model_latency_ms"),
                            "retry_wait_ms": step.get("retry_wait_ms"),
                        },
                    )
            except Exception:
                # Tracing must never crash production execution
                pass

        return record

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single run trace by id."""
        return self.store.get_trace(run_id)

    def list_runs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lists recent run traces."""
        return self.store.list_traces(limit=limit, offset=offset)
