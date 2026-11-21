"""
app/llm/client.py - Provider-agnostic LLM client with structured JSON parsing,
schema validation, per-call latency & token tracking, and automatic one-shot retry.
"""

import json
import re
from typing import Type, TypeVar, Optional, Generic, Dict, Any
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.llm.providers import (
    BaseLLMProvider,
    LLMResponse,
    GeminiProvider,
    GroqProvider,
    OpenAIProvider,
    MockLLMProvider,
)

T = TypeVar("T", bound=BaseModel)


class StructuredResponse(BaseModel, Generic[T]):
    data: T
    raw_text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: float
    model_latency_ms: float = 0.0
    retry_wait_ms: float = 0.0
    retry_attempts: int = 0
    fallback_used: bool = False
    model: str
    provider: str
    retried: bool = False


def extract_json_str(text: str) -> str:
    """Extracts JSON string, handling markdown code fences if present."""
    text = text.strip()
    # Check for markdown code fences ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


class LLMClient:
    """Unified client providing text and schema-validated JSON completions."""

    def __init__(
        self,
        provider: Optional[str] = None,
        custom_provider: Optional[BaseLLMProvider] = None,
        allow_fallback: bool = True,
    ):
        self.allow_fallback = allow_fallback
        if custom_provider:
            self.provider = custom_provider
            self.provider_name = "custom"
            return

        provider_name = (provider or settings.DEFAULT_LLM_PROVIDER).lower()
        self.provider_name = provider_name

        if provider_name == "gemini":
            if not settings.GEMINI_API_KEY:
                # Fallback to mock if key not set (clean test/offline operation)
                self.provider = MockLLMProvider()
                self.provider_name = "mock"
            else:
                fallback_provider = None
                if allow_fallback and settings.GROQ_API_KEY:
                    fallback_provider = GroqProvider(api_key=settings.GROQ_API_KEY)
                self.provider = GeminiProvider(
                    api_key=settings.GEMINI_API_KEY,
                    fallback_provider=fallback_provider,
                )
        elif provider_name == "groq":
            if not settings.GROQ_API_KEY:
                self.provider = MockLLMProvider()
                self.provider_name = "mock"
            else:
                self.provider = GroqProvider(api_key=settings.GROQ_API_KEY)
        elif provider_name == "openai":
            if not settings.OPENAI_API_KEY:
                self.provider = MockLLMProvider()
                self.provider_name = "mock"
            else:
                self.provider = OpenAIProvider(api_key=settings.OPENAI_API_KEY)
        elif provider_name == "mock":
            self.provider = MockLLMProvider()
        else:
            raise ValueError(f"Unsupported LLM provider: {provider_name}")

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Raw generation through provider."""
        return await self.provider.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            model=model,
            temperature=temperature,
            json_mode=json_mode,
        )

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> StructuredResponse[T]:
        """
        Generates completion and parses it into the target Pydantic model.
        If JSON parsing or validation fails, retries once with the error message.
        """
        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        schema_instruction = (
            f"\nYou MUST respond with valid JSON matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Do not include any text before or after the JSON."
        )

        full_prompt = f"{prompt}\n{schema_instruction}"
        initial_res = await self.generate(
            prompt=full_prompt,
            system_instruction=system_instruction,
            model=model,
            temperature=temperature,
            json_mode=True,
        )

        total_duration = initial_res.duration_ms
        prompt_tokens = initial_res.prompt_tokens
        completion_tokens = initial_res.completion_tokens
        total_tokens = initial_res.total_tokens

        # Attempt parse 1
        try:
            clean_json = extract_json_str(initial_res.content)
            parsed_dict = json.loads(clean_json)
            validated_obj = response_model.model_validate(parsed_dict)
            return StructuredResponse(
                data=validated_obj,
                raw_text=initial_res.content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=round(total_duration, 2),
                model_latency_ms=getattr(initial_res, "model_latency_ms", total_duration),
                retry_wait_ms=getattr(initial_res, "retry_wait_ms", 0.0),
                retry_attempts=getattr(initial_res, "retry_attempts", 0),
                fallback_used=getattr(initial_res, "fallback_used", False),
                model=initial_res.model,
                provider=initial_res.provider,
                retried=False,
            )
        except (json.JSONDecodeError, ValidationError) as err:
            parse_error = str(err)

        # Retry once with error feedback as required by Section 7
        retry_prompt = (
            f"{full_prompt}\n\n"
            f"Your last output was invalid JSON or failed schema validation: {parse_error}\n"
            f"Output from previous attempt:\n{initial_res.content}\n\n"
            f"Please output strictly valid JSON conforming exactly to the schema."
        )

        retry_res = await self.generate(
            prompt=retry_prompt,
            system_instruction=system_instruction,
            model=model,
            temperature=temperature,
            json_mode=True,
        )

        total_duration += retry_res.duration_ms
        prompt_tokens += retry_res.prompt_tokens
        completion_tokens += retry_res.completion_tokens
        total_tokens += retry_res.total_tokens

        try:
            clean_json = extract_json_str(retry_res.content)
            parsed_dict = json.loads(clean_json)
            validated_obj = response_model.model_validate(parsed_dict)
            return StructuredResponse(
                data=validated_obj,
                raw_text=retry_res.content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=round(total_duration, 2),
                model_latency_ms=getattr(retry_res, "model_latency_ms", total_duration),
                retry_wait_ms=getattr(initial_res, "retry_wait_ms", 0.0) + getattr(retry_res, "retry_wait_ms", 0.0),
                retry_attempts=getattr(initial_res, "retry_attempts", 0) + getattr(retry_res, "retry_attempts", 0),
                fallback_used=getattr(initial_res, "fallback_used", False) or getattr(retry_res, "fallback_used", False),
                model=retry_res.model,
                provider=retry_res.provider,
                retried=True,
            )
        except (json.JSONDecodeError, ValidationError) as final_err:
            raise ValueError(
                f"Failed to generate valid structured output for {response_model.__name__} after retry: {final_err}"
            ) from final_err
