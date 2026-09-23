"""The only path to a model. Nothing outside this package knows which provider is active."""

import asyncio
from typing import Protocol, TypeVar

from pydantic import BaseModel

from standup.config import MODEL_CATALOG, canonical_model, provider_from_key, settings
from standup.core.llm.anthropic_client import LLMClient
from standup.core.llm.gemini_client import GeminiClient
from standup.core.llm.openai_client import OpenAIClient
from standup.errors import NotConfigured

T = TypeVar("T", bound=BaseModel)

PROVIDERS = {"anthropic": LLMClient, "gemini": GeminiClient, "openai": OpenAIClient}


class ModelClient(Protocol):
    """What every provider offers. Add one by writing it and listing it in PROVIDERS."""

    input_tokens: int
    output_tokens: int

    async def text(
        self, prompt: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> str: ...

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T: ...

    async def describe_image(
        self, data: bytes, media_type: str, *, prompt: str, max_tokens: int | None = None
    ) -> str: ...

    async def aclose(self) -> None: ...


def active_provider() -> str | None:
    """The provider that would be used, or None if nothing is configured."""
    if settings.llm_provider:
        return settings.llm_provider
    if settings.model_api_key:
        return provider_from_key(settings.model_api_key)
    return next((name for name, kind in PROVIDERS.items() if kind.configured()), None)


def active_model() -> str | None:
    """The model that would be called, resolved from MODEL_NAME/LLM_MODEL or the provider's default."""
    chosen = active_provider()
    if chosen is None or chosen not in PROVIDERS:
        return None
    return settings.model_for(PROVIDERS[chosen].default_model)


def from_settings() -> ModelClient:
    """Configuration decides the provider, never a failed request. Failover would hide a fault."""
    chosen = active_provider()
    if chosen is None:
        if settings.model_api_key:
            raise NotConfigured(
                "Could not detect a provider from MODEL_API_KEY. Use an Anthropic (sk-ant-...), "
                "Gemini (AIza...), or OpenAI (sk-...) key, or set LLM_PROVIDER explicitly."
            )
        raise NotConfigured(
            "No model key. Set MODEL_API_KEY in .env (an Anthropic, Gemini, or OpenAI key)."
        )
    if chosen not in PROVIDERS:
        raise NotConfigured(f"LLM_PROVIDER must be one of {sorted(PROVIDERS)}, not {chosen!r}")
    return PROVIDERS[chosen].from_settings()


def describe_image_sync(data: bytes, media_type: str, *, prompt: str) -> str:
    """A bridge for callers that cannot await, like document indexing — the one place indexing
    calls the model. Only safe off the event loop thread; indexing already runs on a worker one."""

    async def _call() -> str:
        client = from_settings()
        try:
            return await client.describe_image(data, media_type, prompt=prompt)
        finally:
            await client.aclose()

    return asyncio.run(_call())


__all__ = [
    "MODEL_CATALOG",
    "PROVIDERS",
    "GeminiClient",
    "LLMClient",
    "ModelClient",
    "OpenAIClient",
    "active_model",
    "active_provider",
    "canonical_model",
    "describe_image_sync",
    "from_settings",
]
