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
    timeout_seconds: float = 90.0,
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
            # Daily quota exhaustion cannot be resolved by short backoff retries; fail fast to allow model/provider fallback
            if "tokens per day" in err_str or "tpd" in err_str or "requests per day" in err_str or "free_tier_requests" in err_str:
                raise

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
        self.client = AsyncGroq(api_key=api_key, max_retries=0)
        self.exhausted_until: Dict[str, float] = {}

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
        models_priority = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
        ]
        initial_target = model if (model and ("gpt" in model or "qwen" in model or "llama" in model)) else "openai/gpt-oss-120b"
        candidate_models = [initial_target] + [m for m in models_priority if m != initial_target]
        now = time.time()
        viable_models = [m for m in candidate_models if now >= self.exhausted_until.get(m, 0)]
        if not viable_models:
            viable_models = candidate_models

        start_time = time.perf_counter()
        response = None
        last_error = None
        used_model = viable_models[0]

        for outer_attempt in range(2):
            for target_model in viable_models:
                used_model = target_model
                async def _call():
                    return await self.client.chat.completions.create(
                        model=target_model,
                        messages=messages,
                        temperature=temperature,
                        response_format=response_format,
                    )

                try:
                    response, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(_call)
                    self.exhausted_until.pop(target_model, None)
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if "tokens per day" in err_str or "tpd" in err_str or "requests per day" in err_str or "rpd" in err_str:
                        self.exhausted_until[target_model] = time.time() + 180.0
                        last_error = e
                        continue
                    elif "rate_limit" in err_str or "429" in err_str:
                        # Momentary per-minute rate limit: sleep 4s and retry same model before falling back
                        await asyncio.sleep(4.0)
                        try:
                            response, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(_call)
                            self.exhausted_until.pop(target_model, None)
                            break
                        except Exception as e2:
                            last_error = e2
                        continue
                    else:
                        raise

            if response is not None:
                break
            await asyncio.sleep(2.0)

        # Fallback: if all viable models failed, try any model on cooldown just in case its window cleared
        if response is None:
            for target_model in candidate_models:
                used_model = target_model
                async def _fb_call():
                    return await self.client.chat.completions.create(
                        model=target_model,
                        messages=messages,
                        temperature=temperature,
                        response_format=response_format,
                    )
                try:
                    response, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(_fb_call)
                    self.exhausted_until.pop(target_model, None)
                    break
                except Exception as e:
                    last_error = e

        if response is None:
            raise last_error or RuntimeError("All candidate Groq models exhausted")

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
            model=used_model,
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
        try:
            response, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(_call)
        except Exception as e:
            err_str = str(e).lower()
            if ("rate_limit" in err_str or "429" in err_str or "tokens per day" in err_str) and target_model != "openai/gpt-oss-20b":
                self.exhausted_models.add(target_model)
                target_model = "openai/gpt-oss-20b"
                async def _fb_call():
                    return await self.client.chat.completions.create(
                        model=target_model,
                        messages=messages,
                        temperature=temperature,
                        response_format=response_format,
                    )
                response, model_latency_ms, retry_wait_ms, retry_attempts = await execute_with_backoff(_fb_call)
            else:
                raise
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
        
        # Test fixture hook: allow deterministic scenario simulation via prompt prefix
        # Only active when provider == 'mock'
        if prompt.startswith("[SCENARIO:CLARIFICATION]"):
            text = json.dumps({
                "intent": "needs_clarification",
                "relevant_tables": ["users", "orders"],
                "relevant_columns": {"users": ["id", "status"], "orders": ["id", "user_id"]},
                "needs_clarification": True,
                "clarification_question": "Does 'active users' mean accounts active in the last 30 days, or accounts with active status?",
                "reasoning_summary": "Ambiguous active user term requires clarification."
            })
        elif prompt.startswith("[SCENARIO:APPROVAL]"):
            text = json.dumps({
                "intent": "analytical_question",
                "relevant_tables": ["customers", "products"],
                "relevant_columns": {"customers": ["customer_name"], "products": ["product_name"]},
                "needs_clarification": False,
                "clarification_question": None,
                "reasoning_summary": "Selecting all customers and products.",
                "sql": "SELECT c.customer_name, p.product_name FROM customers c CROSS JOIN products p",
                "tables_used": ["customers", "products"],
                "confidence": 1.0
            })
        elif prompt.startswith("[SCENARIO:RETRY]"):
            # On first invocation, produce invalid syntax to trigger retry; on second, valid SQL
            if getattr(self, "_retry_counter", 0) == 0:
                self._retry_counter = 1
                text = json.dumps({
                    "sql": "SELEC customer_name FORM customers",  # Syntax error
                    "reasoning_summary": "Attempting customer selection.",
                    "tables_used": ["customers"],
                    "confidence": 0.8
                })
            else:
                self._retry_counter = 0
                text = json.dumps({
                    "sql": "SELECT customer_name FROM customers LIMIT 5",
                    "reasoning_summary": "Repaired syntax error.",
                    "tables_used": ["customers"],
                    "confidence": 1.0,
                    "summary": "Retrieved 5 customers following autonomous repair loop.",
                    "key_points": ["Syntax repaired on retry 1/3"],
                    "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
                    "caveats": []
                })
        elif prompt.startswith("[SCENARIO:EMPTY_RESULT]"):
            text = json.dumps({
                "intent": "analytical_question",
                "relevant_tables": ["customers"],
                "relevant_columns": {"customers": ["customer_name", "annual_spend"]},
                "needs_clarification": False,
                "clarification_question": None,
                "reasoning_summary": "Querying customers with extreme threshold.",
                "sql": "SELECT customer_name FROM customers WHERE annual_spend > 999999999 LIMIT 5",
                "tables_used": ["customers"],
                "confidence": 1.0,
                "summary": "Query executed cleanly but returned 0 rows matching criteria.",
                "key_points": ["Zero records matched spending threshold."],
                "chart": {"chart_type": "table_only", "x": None, "y": None, "title": None},
                "caveats": []
            })
        elif prompt.startswith("[SCENARIO:SUCCESS]"):
            text = json.dumps({
                "intent": "analytical_question",
                "relevant_tables": ["products", "categories", "order_items"],
                "relevant_columns": {"products": ["product_name"], "categories": ["category_name"], "order_items": ["subtotal"]},
                "needs_clarification": False,
                "clarification_question": None,
                "reasoning_summary": "Aggregating product sales.",
                "sql": "SELECT p.product_name, c.category_name, SUM(oi.subtotal) AS total_revenue FROM products p JOIN categories c ON p.category_id = c.category_id JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_id, p.product_name, c.category_name ORDER BY total_revenue DESC LIMIT 5",
                "tables_used": ["products", "categories", "order_items"],
                "confidence": 0.98,
                "summary": "Top 5 products by revenue for completed orders:\\n\\n1. Quantum Ultrabook: $142,500\\n2. ProDisplay 4K: $98,400\\n3. ErgoFlex Chair: $74,200\\n4. SoundWave ANC: $58,350\\n5. KeyMaster Pro: $34,800",
                "key_points": ["Quantum Ultrabook accounts for the largest share", "Top 5 products represent over 40% of sales"],
                "chart_suggestion": {"chart_type": "bar", "x_column": "product_name", "y_column": "total_revenue", "title": "Top 5 Products Revenue"},
                "caveats": []
            })
        elif self._index < len(self.responses):
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
