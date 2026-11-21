"""
app/agents/explainer.py - Explainer Agent.
Translates SQL execution results into plain-language business insights and chart suggestions.
"""

import json
from typing import Dict, Any, Optional, List

from app.config import settings
from app.llm.client import LLMClient, StructuredResponse
from app.agents.models import Explanation
from app.agents.prompt_loader import load_prompt
from app.guardrails.injection import wrap_untrusted_data


class ExplainerAgent:
    """Agent that translates query results into user-facing narrative explanations and chart recommendations."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.system_prompt = load_prompt("explainer.md")

    async def explain(
        self,
        question: str,
        sql: str,
        execution_result: Dict[str, Any],
    ) -> StructuredResponse[Explanation]:
        """Explains execution results in plain language with chart recommendations."""
        columns = execution_result.get("columns", [])
        raw_rows = execution_result.get("rows", [])
        row_count = execution_result.get("row_count", len(raw_rows))
        is_truncated = execution_result.get("truncated", False)

        # Cap preview rows to first 25 for prompt efficiency and security
        preview_rows = raw_rows[:25]

        # Format tabular preview
        formatted_result = {
            "columns": columns,
            "total_rows_found": row_count,
            "is_truncated": is_truncated,
            "preview_rows": preview_rows,
        }

        wrapped_results = wrap_untrusted_data(formatted_result, label="Database Execution Results")
        prompt = (
            f"User Question: {question}\n\n"
            f"SQL Executed:\n```sql\n{sql}\n```\n\n"
            f"{wrapped_results}\n\n"
            f"Please synthesize the data above into a clear plain-language explanation, key takeaways citing specific numbers, and chart suggestion."
        )

        return await self.llm.generate_structured(
            prompt=prompt,
            response_model=Explanation,
            system_instruction=self.system_prompt,
            model=settings.EXPLAINER_MODEL,
            temperature=settings.EXPLAINER_TEMPERATURE,
        )
