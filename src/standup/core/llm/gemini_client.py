"""Gemini through AI Studio, offering the Anthropic client's contract over a different wire."""

from __future__ import annotations

from typing import Any

from standup.core.llm.http_client import JSONHTTPClient
from standup.errors import Upstream

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _spoken(body: dict[str, Any]) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        raise Upstream(f"Gemini returned no candidates: {body.get('promptFeedback', body)}")

    said = "".join(part.get("text", "") for part in candidates[0].get("content", {}).get("parts", []))
    if not said:
        # A thinking model spends maxOutputTokens before it answers; a small budget starves it.
        raise Upstream(f"Gemini said nothing, finishing on {candidates[0].get('finishReason')}")
    return said


class GeminiClient(JSONHTTPClient):
    """The Gemini half of the model seam."""

    provider = "Gemini"
    key = "gemini"
    default_model = "gemini-flash-lite-latest"
    default_base_url = BASE_URL

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
        super().__init__(
            api_key=api_key,
            key_env="MODEL_API_KEY",
            model=model,
            max_tokens=max_tokens,
            max_concurrency=max_concurrency,
            timeout=timeout,
            base_url=base_url or BASE_URL,
            headers={"x-goog-api-key": api_key},
        )

    def _image_parts(self, encoded: str, media_type: str, prompt: str) -> list[dict[str, Any]]:
        return [
            {"inlineData": {"mimeType": media_type, "data": encoded}},
            {"text": prompt},
        ]

    async def _generate(
        self,
        prompt: str | list[dict[str, Any]],
        system: str | None,
        max_tokens: int | None,
        *,
        as_json: bool,
    ) -> str:
        config: dict[str, Any] = {"maxOutputTokens": max_tokens or self._max_tokens}
        if as_json:
            config["responseMimeType"] = "application/json"

        parts = [{"text": prompt}] if isinstance(prompt, str) else prompt
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": config,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        response = await self._post(f"/models/{self._model}:generateContent", body)
        payload = response.json()
        usage = payload.get("usageMetadata", {})
        self.input_tokens += usage.get("promptTokenCount", 0)
        self.output_tokens += usage.get("candidatesTokenCount", 0)
        return _spoken(payload)
