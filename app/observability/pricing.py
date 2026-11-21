"""
app/observability/pricing.py - Configurable price table and cost estimation.
Calculates estimated USD cost based on model, prompt tokens, and completion tokens.
All cost calculations are explicitly marked as estimates.

=== PRICING METADATA & SOURCES ===
- Date of Pricing Table: November 2026 (Updated with current published rates)
- Pricing Sources:
  1. Google Gemini API:
     - URL: https://ai.google.dev/pricing
     - gemini-3.1-flash-lite / gemini-2.5-flash / gemini-1.5-flash: $0.075 per 1M input tokens, $0.30 per 1M output tokens (prompts <= 128k).
     - gemini-1.5-pro: $1.25 per 1M input tokens, $5.00 per 1M output tokens (prompts <= 128k).
  2. Groq Cloud:
     - URL: https://groq.com/pricing
     - openai/gpt-oss-120b: $0.15 per 1M input tokens, $0.60 per 1M output tokens.
     - llama-3.3-70b-versatile: $0.59 per 1M input tokens, $0.79 per 1M output tokens.
  3. OpenAI API:
     - URL: https://openai.com/api/pricing
     - gpt-4o-mini: $0.15 per 1M input tokens, $0.60 per 1M output tokens.
     - gpt-4o: $2.50 per 1M input tokens, $10.00 per 1M output tokens.
  4. Local / Mock:
     - mock-model: $0.00.
"""

from typing import Dict, Any, Optional

PRICING_TABLE_DATE = "2026-11-20"
PRICING_PROVENANCE = "unverified: estimates based on published tier documentation"
PRICING_SOURCES = {
    "gemini": "https://ai.google.dev/pricing",
    "groq": "https://groq.com/pricing",
    "openai": "https://openai.com/api/pricing",
}

# Pricing in USD per 1,000,000 tokens (Input, Output)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Google Gemini
    "gemini-3.1-flash-lite": {
        "input_per_million": 0.075,
        "output_per_million": 0.30,
    },
    "gemini-2.5-flash": {
        "input_per_million": 0.075,
        "output_per_million": 0.30,
    },
    "gemini-1.5-flash": {
        "input_per_million": 0.075,
        "output_per_million": 0.30,
    },
    "gemini-1.5-pro": {
        "input_per_million": 1.25,
        "output_per_million": 5.00,
    },
    # Groq / Open Models
    "openai/gpt-oss-120b": {
        "input_per_million": 0.15,
        "output_per_million": 0.60,
    },
    "llama-3.3-70b-versatile": {
        "input_per_million": 0.59,
        "output_per_million": 0.79,
    },
    "llama3-70b-8192": {
        "input_per_million": 0.59,
        "output_per_million": 0.79,
    },
    # OpenAI
    "gpt-4o-mini": {
        "input_per_million": 0.15,
        "output_per_million": 0.60,
    },
    "gpt-4o": {
        "input_per_million": 2.50,
        "output_per_million": 10.00,
    },
    # Mock / Testing / Local
    "mock-model": {
        "input_per_million": 0.0,
        "output_per_million": 0.0,
    },
    "default": {
        "input_per_million": 0.10,
        "output_per_million": 0.40,
    },
}


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Dict[str, Any]:
    """
    Computes estimated cost in USD for a given model and token counts.
    Returns:
        dict with estimated_cost_usd, prompt_cost_usd, completion_cost_usd, and is_estimate flag.
    """
    pricing = MODEL_PRICING.get(model.lower())
    if not pricing:
        # Fallback to default pricing
        pricing = MODEL_PRICING["default"]

    input_rate = pricing["input_per_million"] / 1_000_000.0
    output_rate = pricing["output_per_million"] / 1_000_000.0

    prompt_cost = prompt_tokens * input_rate
    completion_cost = completion_tokens * output_rate
    total_cost = prompt_cost + completion_cost

    return {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": round(total_cost, 6),
        "prompt_cost_usd": round(prompt_cost, 6),
        "completion_cost_usd": round(completion_cost, 6),
        "is_estimate": True,
        "provenance": PRICING_PROVENANCE,
    }
