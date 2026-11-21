"""
tests/test_llm.py - Verifies LLMClient token capture, latency tracking,
JSON parsing, and one-shot retry mechanism.
"""

import pytest
from pydantic import BaseModel, Field
from typing import List

from app.llm.client import LLMClient
from app.llm.providers import MockLLMProvider


class SampleOutput(BaseModel):
    query_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    tables: List[str]


@pytest.mark.asyncio
async def test_llm_structured_success():
    """Smoke test: calls LLM wrapper and returns validated Pydantic model with token & latency metrics."""
    valid_json = '{"query_name": "top_customers", "confidence": 0.95, "tables": ["customers", "orders"]}'
    mock_provider = MockLLMProvider(responses=[valid_json])
    client = LLMClient(custom_provider=mock_provider)

    res = await client.generate_structured(
        prompt="Find top customers",
        response_model=SampleOutput,
        system_instruction="You are a data assistant.",
    )

    assert isinstance(res.data, SampleOutput)
    assert res.data.query_name == "top_customers"
    assert res.data.confidence == 0.95
    assert res.data.tables == ["customers", "orders"]
    assert res.prompt_tokens > 0
    assert res.completion_tokens > 0
    assert res.total_tokens == res.prompt_tokens + res.completion_tokens


@pytest.mark.asyncio
async def test_gemini_503_groq_fallback(monkeypatch):
    """
    Verifies that when Gemini returns repeated 503 / UNAVAILABLE errors,
    the client transparently falls back to the configured fallback provider (e.g. Groq).
    """
    from app.llm.providers import GeminiProvider, MockLLMProvider

    class Mock503Error(Exception):
        def __init__(self):
            super().__init__("The service is temporarily unavailable (503 Service Unavailable).")
            self.status_code = 503

    fallback_called = False

    class MockGroqFallback(MockLLMProvider):
        async def generate(self, prompt, **kwargs):
            nonlocal fallback_called
            fallback_called = True
            res = await super().generate(prompt, **kwargs)
            res.provider = "groq"
            return res

    fallback = MockGroqFallback(responses=['{"query_name": "fallback_query", "confidence": 0.99, "tables": ["categories"]}'])

    # Avoid real sleep in tests
    async def mock_sleep(s):
        pass

    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    # Instantiate GeminiProvider with fallback
    gemini = GeminiProvider(api_key="fake-key-for-test", fallback_provider=fallback)

    # Mock the underlying genai call to fail with 503 repeatedly
    async def failing_generate_content(*args, **kwargs):
        raise Mock503Error()

    gemini.client.aio.models.generate_content = failing_generate_content

    # Call Gemini generate
    res = await gemini.generate("test prompt", json_mode=True)

    assert fallback_called is True
    assert res.provider == "groq"
    assert "fallback_query" in res.content
    assert res.duration_ms > 0
    assert res.retry_attempts >= 1


@pytest.mark.asyncio
async def test_llm_structured_retry_on_invalid_json():
    """Tests automatic retry when initial LLM response is malformed."""
    malformed = "I cannot provide JSON right now. Here is plain text."
    valid_json = '{"query_name": "recovered_query", "confidence": 0.88, "tables": ["products"]}'

    mock_provider = MockLLMProvider(responses=[malformed, valid_json])
    client = LLMClient(custom_provider=mock_provider)

    res = await client.generate_structured(
        prompt="List products",
        response_model=SampleOutput,
    )

    assert isinstance(res.data, SampleOutput)
    assert res.data.query_name == "recovered_query"
    assert res.data.tables == ["products"]
    assert res.retried is True
    # Tokens and duration should reflect cumulative calls
    assert res.total_tokens > 0


@pytest.mark.asyncio
async def test_llm_structured_failure_after_retry():
    """Tests that client raises ValueError if both attempts fail schema validation."""
    invalid_json_1 = "bad response 1"
    invalid_json_2 = "bad response 2"

    mock_provider = MockLLMProvider(responses=[invalid_json_1, invalid_json_2])
    client = LLMClient(custom_provider=mock_provider)

    with pytest.raises(ValueError, match="Failed to generate valid structured output"):
        await client.generate_structured(
            prompt="List products",
            response_model=SampleOutput,
        )
