"""
app/observability/store.py - Persistent SQLite trace store.
Persists execution traces, latency metrics, token usage, guardrail events,
and estimated costs to a local SQLite database (data/traces.db).
"""

import os
import json
import sqlite3
import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.observability.pricing import estimate_cost


def get_trace_db_path() -> str:
    """Returns absolute path to traces database file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "traces.db")


class TraceStore:
    """Persistent storage and retrieval for QueryPilot execution traces."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_trace_db_path()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable WAL for high concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS traces (
                        run_id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        question TEXT NOT NULL,
                        final_status TEXT NOT NULL,
                        sql TEXT,
                        total_tokens INTEGER DEFAULT 0,
                        prompt_tokens INTEGER DEFAULT 0,
                        completion_tokens INTEGER DEFAULT 0,
                        total_latency_ms REAL DEFAULT 0.0,
                        model_latency_ms REAL DEFAULT 0.0,
                        retry_wait_ms REAL DEFAULT 0.0,
                        retry_count INTEGER DEFAULT 0,
                        estimated_cost_usd REAL DEFAULT 0.0,
                        steps JSON,
                        guardrail_events JSON,
                        explanation JSON
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces (timestamp DESC)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_status ON traces (final_status)")
        finally:
            conn.close()

    def save_run(
        self,
        run_id: str,
        question: str,
        final_status: str,
        sql: Optional[str],
        trace: List[Dict[str, Any]],
        explanation: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Processes raw graph trace events, calculates aggregated metrics & cost,
        and persists the record into traces.db.
        """
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Separate steps from guardrail events
        steps = []
        guardrail_events = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        total_latency_ms = 0.0
        total_model_latency_ms = 0.0
        total_retry_wait_ms = 0.0
        total_cost_usd = 0.0

        for item in trace:
            if item.get("type") == "guardrail_event":
                guardrail_events.append(item)
            else:
                steps.append(item)
                pt = item.get("prompt_tokens", 0) or 0
                ct = item.get("completion_tokens", 0) or 0
                tt = item.get("total_tokens", pt + ct) or 0
                total_prompt_tokens += pt
                total_completion_tokens += ct
                total_tokens += tt

                dur = item.get("duration_ms", 0.0) or 0.0
                total_latency_ms += dur

                mlat = item.get("model_latency_ms", dur) or dur
                total_model_latency_ms += mlat

                rwait = item.get("retry_wait_ms", 0.0) or 0.0
                total_retry_wait_ms += rwait

                # Calculate item cost if LLM step
                model_name = item.get("model", "")
                if model_name and model_name not in ("mcp-server", "sqlglot-deterministic"):
                    cost_info = estimate_cost(model_name, pt, ct)
                    total_cost_usd += cost_info["estimated_cost_usd"]

        record = {
            "run_id": run_id,
            "timestamp": timestamp,
            "question": question,
            "final_status": final_status,
            "sql": sql,
            "total_tokens": total_tokens,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_latency_ms": round(total_latency_ms, 2),
            "model_latency_ms": round(total_model_latency_ms, 2),
            "retry_wait_ms": round(total_retry_wait_ms, 2),
            "retry_count": retry_count,
            "estimated_cost_usd": round(total_cost_usd, 6),
            "steps": steps,
            "guardrail_events": guardrail_events,
            "explanation": explanation,
        }

        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO traces (
                        run_id, timestamp, question, final_status, sql,
                        total_tokens, prompt_tokens, completion_tokens,
                        total_latency_ms, model_latency_ms, retry_wait_ms,
                        retry_count, estimated_cost_usd, steps, guardrail_events, explanation
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        timestamp,
                        question,
                        final_status,
                        sql,
                        total_tokens,
                        total_prompt_tokens,
                        total_completion_tokens,
                        round(total_latency_ms, 2),
                        round(total_model_latency_ms, 2),
                        round(total_retry_wait_ms, 2),
                        retry_count,
                        round(total_cost_usd, 6),
                        json.dumps(steps),
                        json.dumps(guardrail_events),
                        json.dumps(explanation) if explanation else None,
                    ),
                )
        finally:
            conn.close()

        return record

    def get_trace(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single trace record by run_id."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM traces WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_traces(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lists recent traces ordered by timestamp descending."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM traces ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cur.fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        if d.get("steps") and isinstance(d["steps"], str):
            d["steps"] = json.loads(d["steps"])
        if d.get("guardrail_events") and isinstance(d["guardrail_events"], str):
            d["guardrail_events"] = json.loads(d["guardrail_events"])
        if d.get("explanation") and isinstance(d["explanation"], str):
            d["explanation"] = json.loads(d["explanation"])
        return d
