"""Any OpenAI-compatible chat completions endpoint — OpenAI itself, or Ollama, LM Studio, vLLM,
OpenRouter, Groq, Together, and the rest — behind the same ModelClient contract.

This is what makes Standup model agnostic rather than vendor specific: any model that speaks the
OpenAI wire format works, pointed at by ``MODEL_BASE_URL`` and named by ``MODEL_NAME``.
"""

from __future__ import annotations

from typing import Any

from standup.core.llm.http_client import JSONHTTPClient
from standup.errors import Upstream

DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _spoken(body: dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise Upstream(f"OpenAI returned no choices: {body}")

    first = choices[0]
    message = first.get("message") or {}
    content = message.get("content")
    # Some compatible servers return the reply as a list of parts rather than one string.
    if isinstance(content, list):
        said = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    else:
        said = content or ""
    if not said:
        finish = first.get("finish_reason")
        suffix = f", finishing on {finish}" if finish else ""
        raise Upstream(f"OpenAI said nothing{suffix}")
    return said


class OpenAIClient(JSONHTTPClient):
    provider = "OpenAI"
    key = "openai"
    default_model = "gpt-4o-mini"
    default_base_url = DEFAULT_BASE_URL

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
            base_url=base_url or DEFAULT_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def _image_parts(self, encoded: str, media_type: str, prompt: str) -> list[dict[str, Any]]:
        return [
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}},
            {"type": "text", "text": prompt},
        ]

    async def _generate(
        self,
        prompt: str | list[dict[str, Any]],
        system: str | None,
        max_tokens: int | None,
        *,
        as_json: bool,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens or self._max_tokens,
        }
        if as_json:
            body["response_format"] = {"type": "json_object"}

        response = await self._post("/chat/completions", body)
        payload = response.json()
        usage = payload.get("usage") or {}
        self.input_tokens += usage.get("prompt_tokens", 0)
        self.output_tokens += usage.get("completion_tokens", 0)
        return _spoken(payload)
