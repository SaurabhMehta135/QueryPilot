"""
app/agents/schema_agent.py - Schema Selection Agent.
Explores database schema through MCP tools and selects relevant tables/columns.
"""

import json
from typing import Dict, Any, Optional, List

from app.config import settings
from app.llm.client import LLMClient, StructuredResponse
from app.mcp_client.client import MCPDatabaseClient
from app.agents.models import SchemaSelection
from app.agents.prompt_loader import load_prompt
from app.guardrails.injection import wrap_untrusted_data, detect_direct_destructive_intent


class SchemaAgent:
    """Agent that identifies relevant tables and columns for a given user query."""

    def __init__(self, llm_client: Optional[LLMClient] = None, mcp_client: Optional[MCPDatabaseClient] = None):
        self.llm = llm_client or LLMClient()
        self.mcp = mcp_client or MCPDatabaseClient()
        self.system_prompt = load_prompt("schema_agent.md")

    async def get_full_schema_summary(self) -> Dict[str, Any]:
        """Reads tables and column descriptions via MCP using a shared session."""
        async with self.mcp as client:
            tables = await client.list_tables()
            schema_summary = {}
            for table in tables:
                desc = await client.describe_table(table)
                if not desc.get("error"):
                    cols = [f"{c['name']} ({c['type']}{' PK' if c['pk'] else ''})" for c in desc.get("columns", [])]
                    fks = [f"{fk['from']} -> {fk['table']}.{fk['to']}" for fk in desc.get("foreign_keys", [])]
                    schema_summary[table] = {
                        "columns": cols,
                        "foreign_keys": fks,
                    }
            return schema_summary

    async def get_low_cardinality_values(self, tables: List[str]) -> Dict[str, List[Any]]:
        """
        Dynamically retrieves distinct values for low-cardinality categorical columns via MCP.
        Strictly excludes sensitive columns (email, phone, and masking configuration).
        Escapes all string values via escape_untrusted_delimiters to neutralize prompt injections.
        """
        from app.guardrails.injection import escape_untrusted_delimiters

        low_card = {}
        sensitive_raw = settings.SENSITIVE_COLUMNS
        if isinstance(sensitive_raw, str):
            sensitive_list = [s.strip().lower() for s in sensitive_raw.split(",")]
        else:
            sensitive_list = [str(s).strip().lower() for s in sensitive_raw]
        sensitive_cols = {s.split(".")[-1] for s in sensitive_list}

        for table in tables:
            try:
                desc = await self.mcp.describe_table(table)
                for col in desc.get("columns", []):
                    c_name = col["name"]
                    c_name_lower = c_name.lower()
                    full_col_name = f"{table}.{c_name}".lower()

                    # Exclude sensitive columns and keywords
                    if (
                        full_col_name in sensitive_list
                        or c_name_lower in sensitive_cols
                        or any(kw in c_name_lower for kw in ("email", "phone", "password", "token", "ssn", "secret", "credit"))
                    ):
                        continue

                    c_type = col.get("type", "").upper()
                    if c_type in ("TEXT", "VARCHAR") or any(kw in c_name_lower for kw in ("status", "state", "method", "type", "category", "rating")):
                        res = await self.mcp.run_readonly_query(
                            f"SELECT DISTINCT {c_name} FROM {table} WHERE {c_name} IS NOT NULL LIMIT 25;",
                            unmasked=True,
                        )
                        rows = res.get("rows", [])
                        vals = []
                        for r in rows:
                            if r and r[0] is not None:
                                v = r[0]
                                if isinstance(v, str):
                                    v = escape_untrusted_delimiters(v)
                                vals.append(v)
                        if 1 < len(vals) <= 20 and not any(len(str(v)) > 50 for v in vals):
                            low_card[f"{table}.{c_name}"] = vals
            except Exception:
                pass
        return low_card

    async def select_schema(
        self,
        question: str,
        clarification_context: Optional[str] = None,
    ) -> StructuredResponse[SchemaSelection]:
        """Analyzes question against MCP schema and returns structured SchemaSelection."""
        # 1. Deterministic pre-check for direct destructive intent
        is_destructive, block_reason = detect_direct_destructive_intent(question)
        if is_destructive:
            data = SchemaSelection(
                relevant_tables=[],
                relevant_columns={},
                intent="destructive_request",
                block_reason=block_reason,
                needs_clarification=False,
                reasoning_summary=f"Blocked: {block_reason}",
            )
            return StructuredResponse(
                data=data,
                raw_text=json.dumps(data.model_dump()),
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                duration_ms=0.1,
                model_latency_ms=0.1,
                retry_wait_ms=0.0,
                retry_attempts=0,
                model="deterministic-precheck",
                provider="local",
            )

        schema_info = await self.get_full_schema_summary()

        wrapped_schema = wrap_untrusted_data(schema_info, label="Available Database Tables and Relationships")
        prompt = (
            f"User Question: {question}\n\n"
            f"{wrapped_schema}\n"
        )
        if clarification_context:
            wrapped_clarification = wrap_untrusted_data(clarification_context, label="User Provided Clarification")
            prompt += f"\n{wrapped_clarification}\n"

        return await self.llm.generate_structured(
            prompt=prompt,
            response_model=SchemaSelection,
            system_instruction=self.system_prompt,
            model=settings.SCHEMA_AGENT_MODEL,
            temperature=settings.SCHEMA_AGENT_TEMPERATURE,
        )
