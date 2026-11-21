"""
app/agents/sql_writer.py - SQL Writer Agent.
Generates SQLite-compliant read-only SQL queries or repairs failed queries.
"""

import json
from typing import Dict, Any, Optional, List

from app.config import settings
from app.llm.client import LLMClient, StructuredResponse
from app.agents.models import SQLProposal
from app.agents.prompt_loader import load_prompt
from app.guardrails.injection import wrap_untrusted_data


class SQLWriterAgent:
    """Agent that produces or repairs SQLite queries based on selected schema context."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.writer_prompt = load_prompt("sql_writer.md")
        self.repair_prompt = load_prompt("sql_repair.md")

    async def write_sql(
        self,
        question: str,
        schema_context: Dict[str, Any],
        previous_sql: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> StructuredResponse[SQLProposal]:
        """Generates a new SQL query or repairs a failed query."""
        is_repair = bool(previous_sql and error_message)
        system_instruction = self.repair_prompt if is_repair else self.writer_prompt

        wrapped_schema = wrap_untrusted_data(schema_context, label="Relevant Schema Context")
        prompt_parts = [
            f"User Question: {question}\n\n",
            f"{wrapped_schema}\n",
        ]

        if is_repair:
            wrapped_sql = wrap_untrusted_data(previous_sql, label="Previous Failed Query")
            wrapped_error = wrap_untrusted_data(error_message, label="Failure / Rejection Reason")
            prompt_parts.extend([
                f"\n{wrapped_sql}\n",
                f"\n{wrapped_error}\n",
                f"Please fix the query and provide a valid, safe, and correct SQLite query.\n",
            ])

        full_prompt = "".join(prompt_parts)

        return await self.llm.generate_structured(
            prompt=full_prompt,
            response_model=SQLProposal,
            system_instruction=system_instruction,
            model=settings.SQL_WRITER_MODEL,
            temperature=settings.SQL_WRITER_TEMPERATURE,
        )
