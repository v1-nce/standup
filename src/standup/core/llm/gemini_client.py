"""Gemini through AI Studio, offering the Anthropic client's contract over a different wire."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from standup.config import settings
from standup.errors import NotConfigured, Upstream

T = TypeVar("T", bound=BaseModel)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _reason(error: httpx.HTTPError) -> str:
    response = getattr(error, "response", None)
    if response is None:
        return str(error)
    with suppress(ValueError, KeyError):
        return f"HTTP {response.status_code}: {response.json()['error']['message']}"
    return f"HTTP {response.status_code}: {response.text[:200]}"


def _spoken(body: dict[str, Any]) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        raise Upstream(f"Gemini returned no candidates: {body.get('promptFeedback', body)}")

    said = "".join(part.get("text", "") for part in candidates[0].get("content", {}).get("parts", []))
    if not said:
        # A thinking model spends maxOutputTokens before it answers; a small budget starves it.
        raise Upstream(f"Gemini said nothing, finishing on {candidates[0].get('finishReason')}")
    return said


class GeminiClient:
    """The Gemini half of the model seam."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int,
        max_concurrency: int,
        timeout: float,
    ) -> None:
        if not api_key:
            raise NotConfigured("No API key. Set GEMINI_API_KEY in .env")
        self._model = model
        self._max_tokens = max_tokens
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._http = httpx.AsyncClient(
            base_url=BASE_URL, timeout=timeout, headers={"x-goog-api-key": api_key}
        )

    @staticmethod
    def configured() -> bool:
        return bool(settings.gemini_api_key)

    @classmethod
    def from_settings(cls) -> GeminiClient:
        return cls(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            max_tokens=settings.llm_max_tokens,
            max_concurrency=settings.llm_max_concurrency,
            timeout=settings.llm_timeout_seconds,
        )

    async def text(
        self, prompt: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        return await self._generate(prompt, system, max_tokens, as_json=False)

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        # Gemini's responseSchema rejects the $refs Pydantic emits for nested models, so the
        # shape is asked for in words and Pydantic remains the thing that enforces it.
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
                raise Upstream(f"Gemini could not produce a {schema.__name__}: {last}") from last

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _generate(
        self, prompt: str, system: str | None, max_tokens: int | None, *, as_json: bool
    ) -> str:
        config: dict[str, Any] = {"maxOutputTokens": max_tokens or self._max_tokens}
        if as_json:
            config["responseMimeType"] = "application/json"

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        async with self._semaphore:
            try:
                response = await self._http.post(
                    f"/models/{self._model}:generateContent", json=body
                )
                response.raise_for_status()
            except httpx.HTTPError as e:
                raise Upstream(f"Gemini request failed: {_reason(e)}") from e

        return _spoken(response.json())
