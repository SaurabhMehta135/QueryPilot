"""
evals/cached_provider.py - Decorator wrapping an LLM provider with persistent disk caching.
Provides automatic prompt hash caching, request throttling, and cache hit tracking.
"""

import time
import asyncio
from typing import Optional
from app.llm.client import LLMResponse
from app.llm.providers import BaseLLMProvider
from evals.cache import compute_cache_key, get_cached_response, set_cached_response


class CachedLLMProvider(BaseLLMProvider):
    def __init__(
        self,
        inner_provider: BaseLLMProvider,
        max_tpm: int = 7000,
        throttle_seconds: float = 1.0,
        bypass_cache: bool = False,
    ):
        self.inner = inner_provider
        self.max_tpm = max_tpm
        self.throttle_seconds = throttle_seconds
        self.bypass_cache = bypass_cache
        self.cache_hits = 0
        self.cache_misses = 0
        self.uncached_model_latency_ms = []
        self.uncached_retry_wait_ms = []
        self.uncached_total_tokens = []
        self.uncached_prompt_tokens = []
        self.uncached_completion_tokens = []
        self._last_call_time = 0.0
        self._token_window: list = []  # list of (timestamp, token_count)

    async def _wait_for_token_bucket(self, est_tokens: int = 2500):
        """Enforces rolling 60-second token-per-minute (TPM) limit."""
        while True:
            now = time.time()
            # Purge entries older than 60 seconds
            self._token_window = [(t, tok) for t, tok in self._token_window if now - t < 60.0]
            current_tpm = sum(tok for _, tok in self._token_window)

            if current_tpm + est_tokens <= self.max_tpm:
                break

            # Need to wait until the oldest entry expires
            if self._token_window:
                sleep_needed = max(0.5, 60.0 - (now - self._token_window[0][0]) + 0.5)
                await asyncio.sleep(sleep_needed)
            else:
                break

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        target_model = model or getattr(self.inner, "default_model", "gemini-3.1-flash-lite")
        provider_name = getattr(self.inner, "provider_name", "gemini")
        cache_key = compute_cache_key(provider_name, target_model, prompt, system_instruction)

        if not self.bypass_cache:
            cached_data = get_cached_response(cache_key)
            if cached_data is not None:
                self.cache_hits += 1
                res = LLMResponse(**cached_data)
                res.duration_ms = 1.0
                res.model_latency_ms = 1.0
                res.retry_wait_ms = 0.0
                return res

        # Throttle by Token-Per-Minute (TPM) bucket
        est_tokens = len(prompt.split()) + 500
        await self._wait_for_token_bucket(est_tokens)

        # Minimum spacing between live calls
        now = time.time()
        elapsed = now - self._last_call_time
        if elapsed < self.throttle_seconds:
            await asyncio.sleep(self.throttle_seconds - elapsed)

        self.cache_misses += 1
        res = await self.inner.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            model=model,
            temperature=temperature,
            json_mode=json_mode,
        )
        self._last_call_time = time.time()
        self._token_window.append((time.time(), res.total_tokens))

        # Track uncached call statistics
        self.uncached_model_latency_ms.append(getattr(res, "model_latency_ms", res.duration_ms))
        self.uncached_retry_wait_ms.append(getattr(res, "retry_wait_ms", 0.0))
        self.uncached_total_tokens.append(res.total_tokens)
        self.uncached_prompt_tokens.append(res.prompt_tokens)
        self.uncached_completion_tokens.append(res.completion_tokens)

        # Cache response
        set_cached_response(cache_key, res.__dict__)
        return res
