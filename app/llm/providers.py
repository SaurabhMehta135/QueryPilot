"""
app/llm/providers.py - Provider adapters for Gemini, Groq, OpenAI, and Mock.
Each provider handles generation, token counts, model latency vs retry wait times,
and 429/503 exponential backoff.
"""

import time
import json
import asyncio
import random
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable, Awaitable, Tuple
from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0          # Total latency (model_latency_ms + retry_wait_ms)
    model_latency_ms: float = 0.0     # Time spent waiting for successful API call
    retry_wait_ms: float = 0.0        # Time spent sleeping during backoff retries
    retry_attempts: int = 0           # Count of rate limit / unavailable retries
    fallback_used: bool = False       # True if secondary provider handled the request
    model: str
    provider: str


async def execute_with_backoff(
    coro_fn: Callable[[], Awaitable[Any]],
    max_retries: int = 6,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    timeout_seconds: float = 45.0,
) -> Tuple[Any, float, float, int]:
    """
    Executes an async API call with exponential backoff on HTTP 429 / 503 / Rate Limit / High Demand errors and socket timeouts.
    Returns: (result, model_latency_ms, retry_wait_ms, retry_attempts)
    """
    delay = initial_delay
    total_wait_ms = 0.0
    retry_attempts = 0

    for attempt in range(max_retries + 1):
        call_start = time.perf_counter()
        try:
            result = await asyncio.wait_for(coro_fn(), timeout=timeout_seconds)
            call_latency_ms = (time.perf_counter() - call_start) * 1000
            return result, round(call_latency_ms, 2), round(total_wait_ms, 2), retry_attempts
        except Exception as e:
            err_str = str(e).lower()
            status_code = getattr(e, "code", getattr(e, "status_code", None))
            is_retryable = (
                isinstance(e, asyncio.TimeoutError)
                or status_code in (429, 503, 502, 504)
                or "429" in err_str
                or "503" in err_str
                or "resource_exhausted" in err_str
                or "rate_limit" in err_str
                or "too many requests" in err_str
                or "high demand" in err_str
                or "unavailable" in err_str
                or "timeout" in err_str
            )
            if is_retryable and attempt < max_retries:
                retry_attempts += 1
                jitter = random.uniform(0.1, 0.5)
                wait_time = delay + jitter
                sleep_start = time.perf_counter()
                await asyncio.sleep(wait_time)
                total_wait_ms += (time.perf_counter() - sleep_start) * 1000
                delay *= backoff_factor
            else:
                raise

    raise RuntimeError("execute_with_backoff failed after retries")


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generates a text completion and returns standard LLMResponse."""
        pass


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, fallback_provider: Optional[BaseLLMProvider] = None):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.fallback_provider = fallback_provider

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = "gemini-3.1-flash-lite",
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json" if json_mode else None,
        )

        target_model = model if (model and "gemini" in model) else "gemini-3.1-flash-lite"

        async def _call():
            return await self.client.aio.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config,
            )

        start_time = time.perf_counter()
        try:
            response, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(_call)
        except Exception as e:
            err_str = str(e).lower()
            is_service_failure = (
                "503" in err_str
                or "unavailable" in err_str
                or "resource_exhausted" in err_str
                or "high demand" in err_str
                or "429" in err_str
                or "rate_limit" in err_str
            )
            if is_service_failure and self.fallback_provider is not None:
                # Fall back to secondary provider (e.g. Groq) after repeated Gemini failures
                fb_res = await self.fallback_provider.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    json_mode=json_mode,
                )
                fb_res.retry_attempts += 1
                fb_res.fallback_used = True
                fb_res.duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return fb_res
            raise

        total_duration_ms = (time.perf_counter() - start_time) * 1000

        text = response.text or ""
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        total_tokens = getattr(usage, "total_token_count", prompt_tokens + completion_tokens) if usage else 0

        return LLMResponse(
            content=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=round(total_duration_ms, 2),
            model_latency_ms=model_latency_ms,
            retry_wait_ms=retry_wait_ms,
            retry_attempts=retry_attempts,
            model=target_model,
            provider="gemini",
        )


class GroqProvider(BaseLLMProvider):
    def __init__(self, api_key: str):
        from groq import AsyncGroq
        self.client = AsyncGroq(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = "openai/gpt-oss-120b",
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response_format = {"type": "json_object"} if json_mode else None
        target_model = model if (model and ("gpt" in model or "qwen" in model or "llama" in model)) else "openai/gpt-oss-120b"

        async def _call():
            return await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
            )

        start_time = time.perf_counter()
        response, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(_call)
        total_duration_ms = (time.perf_counter() - start_time) * 1000

        choice = response.choices[0]
        text = choice.message.content or ""
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens

        return LLMResponse(
            content=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=round(total_duration_ms, 2),
            model_latency_ms=model_latency_ms,
            retry_wait_ms=retry_wait_ms,
            retry_attempts=retry_attempts,
            model=target_model,
            provider="groq",
        )


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = "gpt-4o-mini",
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response_format = {"type": "json_object"} if json_mode else None
        target_model = model or "gpt-4o-mini"

        async def _call():
            return await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
            )

        start_time = time.perf_counter()
        response, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(_call)
        total_duration_ms = (time.perf_counter() - start_time) * 1000

        choice = response.choices[0]
        text = choice.message.content or ""
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens

        return LLMResponse(
            content=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=round(total_duration_ms, 2),
            model_latency_ms=model_latency_ms,
            retry_wait_ms=retry_wait_ms,
            retry_attempts=retry_attempts,
            model=target_model,
            provider="openai",
        )


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider for unit tests and offline testing."""
    def __init__(self, responses: Optional[List[str]] = None):
        self.responses = responses or []
        self._index = 0
        self.recorded_prompts: List[str] = []

    def add_response(self, text: str):
        self.responses.append(text)

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = "mock-model",
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.recorded_prompts.append(prompt)
        if self._index < len(self.responses):
            text = self.responses[self._index]
            self._index += 1
        else:
            if json_mode:
                text = json.dumps({
                    "intent": "analytical_question",
                    "relevant_tables": ["products"],
                    "relevant_columns": {"products": ["product_id", "name"]},
                    "needs_clarification": False,
                    "clarification_question": None,
                    "reasoning_summary": "Mock reasoning summary.",
                    "sql": "SELECT name FROM products LIMIT 5",
                    "tables_used": ["products"],
                    "confidence": 0.95,
                    "summary": "Mock data summary.",
                    "key_points": ["Mock point 1"],
                    "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
                    "caveats": []
                })
            else:
                text = f"Mock response to: {prompt[:50]}"

        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(text) // 4)

        return LLMResponse(
            content=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_ms=1.5,
            model_latency_ms=1.5,
            retry_wait_ms=0.0,
            retry_attempts=0,
            model=model or "mock-model",
            provider="mock",
        )
