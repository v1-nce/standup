"""The only path to a model. Nothing outside this package knows which provider is active."""

from typing import Protocol, TypeVar

from pydantic import BaseModel

from standup.config import settings
from standup.core.llm.client import LLMClient
from standup.core.llm.gemini_client import GeminiClient
from standup.errors import NotConfigured

T = TypeVar("T", bound=BaseModel)

PROVIDERS = {"anthropic": LLMClient, "gemini": GeminiClient}


class ModelClient(Protocol):
    """What every provider offers. Add one by writing it and listing it in PROVIDERS."""

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

    async def aclose(self) -> None: ...


def active_provider() -> str | None:
    """The provider that would be used, or None if nothing is configured."""
    if settings.llm_provider:
        return settings.llm_provider
    return next((name for name, kind in PROVIDERS.items() if kind.configured()), None)


def from_settings() -> ModelClient:
    """Configuration decides the provider, never a failed request. Failover would hide a fault."""
    chosen = active_provider()
    if chosen is None:
        raise NotConfigured("No model key. Set ANTHROPIC_API_KEY or GEMINI_API_KEY in .env")
    if chosen not in PROVIDERS:
        raise NotConfigured(f"LLM_PROVIDER must be one of {sorted(PROVIDERS)}, not {chosen!r}")
    return PROVIDERS[chosen].from_settings()


__all__ = [
    "PROVIDERS",
    "GeminiClient",
    "LLMClient",
    "ModelClient",
    "active_provider",
    "from_settings",
]
