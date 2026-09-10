"""One JSON HTTP transport shared by every provider that speaks a JSON-over-HTTP API.

Gemini and OpenAI-compatible providers both need the same three things — bounded concurrency,
transient retry with capped backoff, and a Pydantic-enforced JSON reply — so they share this base
rather than each carrying a copy. The Anthropic SDK already owns those for its own wire format.
"""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import suppress
from typing import Any, ClassVar, Self, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from standup.config import settings
from standup.errors import NotConfigured, Upstream

T = TypeVar("T", bound=BaseModel)

_RETRIES = 2
_RETRIABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def reason(error: httpx.HTTPError) -> str:
    """A stable, readable message from an HTTP failure, whatever shape the body took."""
    response = getattr(error, "response", None)
    if response is None:
        return str(error)
    with suppress(ValueError, KeyError, TypeError):
        return f"HTTP {response.status_code}: {response.json()['error']['message']}"
    return f"HTTP {response.status_code}: {response.text[:200]}"


class JSONHTTPClient:
    """Base for a provider reached over a JSON HTTP API. Subclasses declare ``provider``,
    ``default_model`` and ``key_attr`` and implement ``_image_parts`` and ``_generate``; transport,
    retry, and JSON validation live here."""

    provider: ClassVar[str] = ""
    default_model: ClassVar[str] = ""
    key_attr: ClassVar[str] = ""

    def __init__(
        self,
        *,
        api_key: str,
        key_env: str,
        model: str,
        max_tokens: int,
        max_concurrency: int,
        timeout: float,
        base_url: str,
        headers: dict[str, str],
    ) -> None:
        if not api_key:
            raise NotConfigured(f"No API key. Set {key_env} in .env")
        self._model = model
        self._max_tokens = max_tokens
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.input_tokens = 0
        self.output_tokens = 0
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, headers=headers)

    @classmethod
    def configured(cls) -> bool:
        return bool(getattr(settings, cls.key_attr))

    @classmethod
    def from_settings(cls) -> Self:
        return cls(
            api_key=getattr(settings, cls.key_attr),
            model=settings.llm_model or cls.default_model,
            max_tokens=settings.llm_max_tokens,
            max_concurrency=settings.llm_max_concurrency,
            timeout=settings.llm_timeout_seconds,
            base_url=settings.llm_base_url,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def text(
        self, prompt: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        return await self._generate(prompt, system, max_tokens, as_json=False)

    async def describe_image(
        self, data: bytes, media_type: str, *, prompt: str, max_tokens: int | None = None
    ) -> str:
        encoded = base64.standard_b64encode(data).decode("ascii")
        return await self._generate(
            self._image_parts(encoded, media_type, prompt), None, max_tokens, as_json=False
        )

    def _image_parts(self, encoded: str, media_type: str, prompt: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        # The response schema is asked for in words and Pydantic remains the thing that enforces
        # it; not every OpenAI-compatible endpoint honours a machine-readable schema, so this is
        # the one path that works across all of them.
        asked = f"{prompt}\n\nReply with JSON matching this schema:\n{json.dumps(schema.model_json_schema())}"
        try:
            return schema.model_validate_json(
                await self._generate(asked, system, max_tokens, as_json=True)
            )
        except ValidationError as first:
            again = f"{asked}\n\nYour previous reply did not match that schema:\n{first}"
            try:
                return schema.model_validate_json(
                    await self._generate(again, system, max_tokens, as_json=True)
                )
            except ValidationError as last:
                raise Upstream(f"{self.provider} could not produce a {schema.__name__}: {last}") from last

    async def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        """Backs off a transient failure. The semaphore covers one attempt, not the whole retry
        loop, so a backing-off request never occupies a concurrency slot while it sleeps."""
        for attempt in range(_RETRIES + 1):
            try:
                async with self._semaphore:
                    response = await self._http.post(path, json=body)
                    response.raise_for_status()
                return response
            except httpx.HTTPError as e:
                retriable = isinstance(e, httpx.TransportError) or (
                    isinstance(e, httpx.HTTPStatusError)
                    and e.response.status_code in _RETRIABLE_STATUS
                )
                if not retriable or attempt == _RETRIES:
                    raise Upstream(f"{self.provider} request failed: {reason(e)}") from e
                await asyncio.sleep(0.5 * 2**attempt)

    async def _generate(
        self,
        prompt: str | list[dict[str, Any]],
        system: str | None,
        max_tokens: int | None,
        *,
        as_json: bool,
    ) -> str:
        raise NotImplementedError
