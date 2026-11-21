# QueryPilot

QueryPilot is a production-grade, multi-agent Text-to-SQL assistant built with LangGraph, Model Context Protocol (MCP), deterministic AST-based SQL guardrails, full observability tracing, Server-Sent Events (SSE) streaming, and an interactive single-page web UI.

---

## Architecture Overview

```
User Question
      │
      ▼
[ Layer 1: Deterministic Pre-Check ] ──────────► Blocked (Refusal)
      │ (safe)
      ▼
[ Layer 2: Schema Agent ] ────────────────────► Needs Clarification (Interrupt)
      │ (intent = analytical_question)
      ▼
[ Layer 3: SQL Writer Agent ]
      │
      ▼
[ Layer 4: SQL Validator & Guardrails ] ──────► Prohibited AST / Syntax Error -> SQL Repair Node
      │                                       ► Expensive Cartesian Join -> Approval Node (Interrupt)
      ▼ (safe & approved)
[ Layer 5: Read-Only Executor (MCP) ]
      │
      ▼
[ Layer 6: Explainer Agent ]
      │
      ▼
Output to UI / API Stream
```

---

## Streaming Architecture & Explanation Streaming

QueryPilot delivers real-time updates to client frontends using **Server-Sent Events (SSE)** via `POST /ask` and `POST /resume`:
- Graph progress events (`run_started`, `node_started`, `sql_generated`, `validation_result`, `execution_result`, `needs_input`, `run_finished`) are pushed as each node executes.
- **Explanation Streaming Clarification**:
  To ensure strict reliability and UI rendering safety, the Explainer Agent leverages `generate_structured(ExplanationReport)` to validate output against a strict Pydantic model (`summary`, `key_points`, `chart`, `caveats`).
  Therefore, explanation streaming is **simulated token-by-token streaming from structured JSON output** (the validated summary text is chunked and streamed token-by-token over SSE with micro-delays) rather than raw unvalidated model token streaming. This eliminates JSON parsing failures and schema truncation.

---

## Guardrails & Security

1. **Deterministic Pre-Check (Layer 1)**: Intercepts raw DDL/DML statements (`DROP`, `DELETE`, `UPDATE`, `TRUNCATE`, `ALTER`) and plain English destructive patterns before LLM invocation.
2. **Untrusted Data Sanitization**: All database content and tool outputs entering LLM prompts are wrapped in `<untrusted_data>...</untrusted_data>` blocks with all `<` and `>` tags escaped.
3. **AST SQL Validation**: Uses `sqlglot` to enforce single-statement read-only `SELECT` queries, reject SQLite internal schemas (`sqlite_master`), apply auto-LIMIT caps (default 100, max 1000), and detect expensive Cartesian products.
4. **CROSS JOIN Single-Row Exemption**: CROSS JOINs between scalar subqueries or aggregate CTEs (e.g., period comparisons) produce 1 row and are recognized as computationally safe.
5. **Sensitive Column Masking**: Reversible regex masking masks PII (e.g. emails, phone numbers) before data reaches LLMs, API responses, or stored traces.

---

## Observability & Pricing Notice

QueryPilot automatically tracks token usage, model latency, retry wait time, and estimated query costs across Gemini, Groq, and OpenAI providers.

> **Note on Pricing Values**: Cost calculations in `app/observability/pricing.py` are **unverified estimates based on published tier documentation** (dated 2026-11-20), rather than scraped live billing APIs.
