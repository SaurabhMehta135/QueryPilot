"""
tests/test_live_llm.py - Live LLM smoke tests and 429 exponential backoff verification.
"""

import os
import pytest
from pydantic import BaseModel
from typing import List

from app.config import Settings
from app.llm.client import LLMClient
from app.llm.providers import execute_with_backoff


class LiveOutputModel(BaseModel):
    category_summary: str
    sample_tags: List[str]


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_llm_smoke(request):
    """Live smoke test: invokes configured provider (Gemini or Groq) if key is present and --run-live passed."""
    if not request.config.getoption("--run-live", default=False):
        pytest.skip("Pass --run-live to run live network LLM tests.")

    live_settings = Settings()
    api_key = live_settings.GEMINI_API_KEY or live_settings.GROQ_API_KEY
    if not api_key:
        pytest.skip("No live LLM API key configured in environment.")

    provider_name = "gemini" if live_settings.GEMINI_API_KEY else "groq"
    client = LLMClient(provider=provider_name)

    res = await client.generate_structured(
        prompt="Categorize e-commerce electronics and list 3 example product tags.",
        response_model=LiveOutputModel,
        system_instruction="You are a JSON categorization assistant.",
    )

    assert isinstance(res.data, LiveOutputModel)
    assert len(res.data.sample_tags) >= 2
    assert res.prompt_tokens > 0
    assert res.completion_tokens > 0
    assert res.duration_ms > 0
    assert res.provider == provider_name


@pytest.mark.asyncio
async def test_429_exponential_backoff_retry(monkeypatch):
    """Verifies that execute_with_backoff catches 429 rate limit errors and retries without real sleeping."""
    call_count = 0
    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)

    # Patch asyncio.sleep so unit test runs instantaneously
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    class MockRateLimitError(Exception):
        def __init__(self, message="Rate limit exceeded: 429 Too Many Requests"):
            super().__init__(message)
            self.status_code = 429

    async def flaky_call():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise MockRateLimitError()
        return "success_after_backoff"

    result, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(
        flaky_call,
        max_retries=2,
        initial_delay=0.05,
        backoff_factor=1.5,
    )

    assert result == "success_after_backoff"
    assert call_count == 2
    assert retry_attempts == 1
    assert len(sleep_calls) == 1
