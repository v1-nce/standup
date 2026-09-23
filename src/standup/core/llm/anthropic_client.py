from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager
from typing import Any, TypeVar

import anthropic
from anthropic.types import Usage
from pydantic import BaseModel

from standup.config import settings
from standup.errors import NotConfigured, Upstream

T = TypeVar("T", bound=BaseModel)
MAX_RETRIES = 2


@contextmanager
def _translated():
    try:
        yield
    except anthropic.AnthropicError as e:
        raise Upstream(str(e)) from e


class LLMClient:
    """The Anthropic half of the model seam."""

    default_model = "claude-opus-5"
    key = "anthropic"

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
            raise NotConfigured("No API key. Set MODEL_API_KEY in .env")
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=MAX_RETRIES
        )
        self._model = model
        self._max_tokens = max_tokens
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.input_tokens = 0
        self.output_tokens = 0

    @staticmethod
    def configured() -> bool:
        return bool(settings.api_key_for("anthropic"))

    @classmethod
    def from_settings(cls) -> LLMClient:
        return cls(
            api_key=settings.api_key_for("anthropic"),
            model=settings.model_for(cls.default_model),
            max_tokens=settings.llm_max_tokens,
            max_concurrency=settings.llm_max_concurrency,
            timeout=settings.llm_timeout_seconds,
            base_url=settings.base_url_for(),
        )

    async def text(
        self, prompt: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        return await self._create(prompt, system, max_tokens)

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
        self._tally(response.usage)
        return response.parsed_output

    async def describe_image(
        self, data: bytes, media_type: str, *, prompt: str, max_tokens: int | None = None
    ) -> str:
        blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(data).decode("ascii"),
                },
            },
            {"type": "text", "text": prompt},
        ]
        return await self._create(blocks, None, max_tokens)

    async def aclose(self) -> None:
        await self._client.close()

    async def _create(
        self, content: str | list[dict[str, Any]], system: str | None, max_tokens: int | None
    ) -> str:
        async with self._semaphore:
            with _translated():
                response = await self._client.messages.create(
                    **self._request(content, system, max_tokens)
                )
        self._tally(response.usage)
        said = "".join(block.text for block in response.content if block.type == "text")
        if not said:
            raise Upstream(f"Claude said nothing, stopping on {response.stop_reason}")
        return said

    def _tally(self, usage: Usage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens

    def _request(
        self, content: str | list[dict[str, Any]], system: str | None, max_tokens: int | None
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens or self._max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if system:
            # The system prompt is re-sent every round unchanged; mark it ephemeral so the
            # provider serves the later rounds from cache instead of re-reading it each time.
            request["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        return request
