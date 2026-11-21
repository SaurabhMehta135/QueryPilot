"""
app/agents/models.py - Pydantic data models for structured agent outputs.
All LLM responses are parsed and validated using these models.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any


class SchemaSelection(BaseModel):
    relevant_tables: List[str] = Field(
        default_factory=list,
        description="List of table names identified as necessary to answer the user question."
    )
    relevant_columns: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping of table name to list of relevant column names."
    )
    intent: Literal["analytical_question", "destructive_request", "needs_clarification", "off_topic"] = Field(
        default="analytical_question",
        description="Classified user intent: analytical_question, destructive_request, needs_clarification, or off_topic."
    )
    block_reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason if query is destructive or prohibited."
    )
    needs_clarification: bool = Field(
        default=False,
        description="Set to true if user question is too vague or ambiguous to answer reliably."
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="Question to present to user if clarification is needed."
    )
    reasoning_summary: str = Field(
        default="",
        description="Brief summary of why these tables and columns were chosen."
    )


class SQLProposal(BaseModel):
    sql: str = Field(
        description="SQLite-compatible SELECT query answering the user question."
    )
    reasoning_summary: str = Field(
        description="Explanation of the query construction, joins, and filters."
    )
    tables_used: List[str] = Field(
        description="List of table names referenced in the query."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 in this query's correctness."
    )


class ValidationResult(BaseModel):
    is_safe: bool = Field(
        description="Whether the SQL query meets all security and read-only criteria."
    )
    reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason if the query was rejected."
    )
    rewritten_sql: Optional[str] = Field(
        default=None,
        description="Modified query (e.g. after adding LIMIT clause)."
    )
    is_expensive: bool = Field(
        default=False,
        description="Whether query was flagged as potentially heavy (missing join/unbounded scan)."
    )


class ChartSuggestion(BaseModel):
    chart_type: Literal["bar", "line", "pie", "scatter", "table_only"] = Field(
        description="Recommended chart type for presenting the result."
    )
    x: Optional[str] = Field(
        default=None,
        description="Column name to use for the X-axis (or category axis)."
    )
    y: Optional[str] = Field(
        default=None,
        description="Column name to use for the Y-axis (or metric axis)."
    )
    title: Optional[str] = Field(
        default=None,
        description="Suggested title for the chart."
    )


class Explanation(BaseModel):
    summary: str = Field(
        description="Direct plain-language summary of the answer."
    )
    key_points: List[str] = Field(
        description="Bulleted key insights or observations from the data."
    )
    chart: ChartSuggestion = Field(
        description="Recommended chart visualization for the data."
    )
    caveats: List[str] = Field(
        default_factory=list,
        description="Any limitations, date bounds, or exclusions applicable to this result."
    )
