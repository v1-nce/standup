from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from standup.config import settings
from standup.errors import NotConfigured, Upstream

T = TypeVar("T", bound=BaseModel)


@contextmanager
def _translated():
    try:
        yield
    except anthropic.AnthropicError as e:
        raise Upstream(str(e)) from e


class LLMClient:
    """The backend's only path to a model."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int,
        max_concurrency: int,
        timeout: float,
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise NotConfigured("No API key. Set ANTHROPIC_API_KEY in .env")
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, base_url=base_url, timeout=timeout
        )
        self._model = model
        self._max_tokens = max_tokens
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @staticmethod
    def configured() -> bool:
        return bool(settings.anthropic_api_key)

    @classmethod
    def from_settings(cls) -> LLMClient:
        return cls(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            max_concurrency=settings.llm_max_concurrency,
            timeout=settings.llm_timeout_seconds,
            base_url=settings.llm_base_url,
        )

    async def text(
        self, prompt: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        async with self._semaphore:
            with _translated():
                response = await self._client.messages.create(
                    **self._request(prompt, system, max_tokens)
                )
        return "".join(block.text for block in response.content if block.type == "text")

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        async with self._semaphore:
            with _translated():
                response = await self._client.messages.parse(
                    **self._request(prompt, system, max_tokens),
                    output_format=schema,
                )
        return response.parsed_output

    async def aclose(self) -> None:
        await self._client.close()

    def _request(self, prompt: str, system: str | None, max_tokens: int | None) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens or self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            request["system"] = system
        return request
