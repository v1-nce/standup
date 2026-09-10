import base64
import json

import httpx
import pytest
from pydantic import BaseModel

from standup.core import llm
from standup.core.llm import http_client
from standup.core.llm.gemini_client import GeminiClient, _spoken
from standup.core.llm.http_client import reason
from standup.core.llm.openai_client import OpenAIClient
from standup.core.llm.openai_client import _spoken as _openai_spoken
from standup.errors import NotConfigured, Upstream


async def _instant(*_args, **_kwargs) -> None:
    """Skips the real backoff delay in tests that force a retry."""


class Shape(BaseModel):
    name: str
    count: int


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_provider", "")
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "")
    monkeypatch.setattr(llm.settings, "gemini_api_key", "")
    monkeypatch.setattr(llm.settings, "openai_api_key", "")
    return llm.settings


def gemini(handler) -> GeminiClient:
    """A real client with its transport swapped, so headers and body building are still exercised."""
    client = GeminiClient(api_key="k", model="m", max_tokens=100, max_concurrency=2, timeout=5.0)
    client._http = httpx.AsyncClient(
        base_url="https://example.invalid",
        headers={"x-goog-api-key": "k"},
        transport=httpx.MockTransport(handler),
    )
    return client


def spoke(text: str, finish: str = "STOP") -> httpx.Response:
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]},
    )


def test_nothing_configured_names_every_key(unconfigured):
    assert llm.active_provider() is None
    with pytest.raises(NotConfigured, match="ANTHROPIC_API_KEY, GEMINI_API_KEY or OPENAI_API_KEY"):
        llm.from_settings()


def test_a_gemini_key_alone_selects_gemini(unconfigured, monkeypatch):
    monkeypatch.setattr(llm.settings, "gemini_api_key", "k")
    assert llm.active_provider() == "gemini"
    assert isinstance(llm.from_settings(), GeminiClient)


def test_anthropic_wins_when_both_are_present(unconfigured, monkeypatch):
    monkeypatch.setattr(llm.settings, "gemini_api_key", "k")
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "k")
    assert llm.active_provider() == "anthropic"


def test_an_openai_key_alone_selects_openai(unconfigured, monkeypatch):
    monkeypatch.setattr(llm.settings, "openai_api_key", "k")
    assert llm.active_provider() == "openai"
    assert isinstance(llm.from_settings(), OpenAIClient)


def test_the_model_setting_overrides_any_providers_default(unconfigured, monkeypatch):
    monkeypatch.setattr(llm.settings, "gemini_api_key", "k")
    monkeypatch.setattr(llm.settings, "llm_model", "my-model")
    assert llm.active_model() == "my-model"
    assert llm.from_settings()._model == "my-model"


def test_active_model_falls_back_to_the_providers_default(unconfigured, monkeypatch):
    monkeypatch.setattr(llm.settings, "gemini_api_key", "k")
    assert llm.active_model() == "gemini-flash-lite-latest"
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "k")
    assert llm.active_model() == "claude-opus-5"


def test_an_explicit_choice_overrides_what_happens_to_be_configured(unconfigured, monkeypatch):
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "k")
    monkeypatch.setattr(llm.settings, "gemini_api_key", "k")
    monkeypatch.setattr(llm.settings, "llm_provider", "gemini")
    assert isinstance(llm.from_settings(), GeminiClient)


def test_an_unknown_provider_is_refused_by_name(unconfigured, monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_provider", "llama")
    with pytest.raises(NotConfigured, match="llama"):
        llm.from_settings()


def test_describe_image_sync_bridges_to_the_async_client_and_closes_it(monkeypatch):
    closed = []

    class Fake:
        async def describe_image(self, data, media_type, *, prompt, max_tokens=None):
            return f"described {media_type}: {prompt}"

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(llm, "from_settings", lambda: Fake())

    result = llm.describe_image_sync(b"bytes", "image/png", prompt="describe it")

    assert result == "described image/png: describe it"
    assert closed == [True]


def test_every_provider_answers_the_same_contract():
    for kind in llm.PROVIDERS.values():
        assert callable(kind.configured)
        assert callable(kind.from_settings)
        assert isinstance(kind.default_model, str) and kind.default_model
        for method in ("text", "structured", "describe_image", "aclose"):
            assert callable(getattr(kind, method))


async def test_text_asks_for_what_it_was_given():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        seen["key"] = request.headers.get("x-goog-api-key")
        return spoke("ready")

    assert await gemini(handler).text("say ready", system="be terse") == "ready"
    assert seen["url"].endswith("/models/m:generateContent")
    assert seen["key"] == "k"
    assert "be terse" in seen["body"]
    assert "responseMimeType" not in seen["body"]


async def test_structured_asks_for_json_and_returns_the_model():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return spoke('{"name": "auth", "count": 3}')

    assert await gemini(handler).structured("go", Shape) == Shape(name="auth", count=3)
    assert "responseMimeType" in seen["body"]
    assert "count" in seen["body"]


async def test_a_reply_of_the_wrong_shape_is_asked_for_again():
    replies = iter([spoke('{"name": "auth"}'), spoke('{"name": "auth", "count": 3}')])
    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.read().decode())
        return next(replies)

    assert await gemini(handler).structured("go", Shape) == Shape(name="auth", count=3)
    assert len(asked) == 2
    assert "did not match" in asked[1]


async def test_a_reply_that_stays_wrong_fails_rather_than_guessing():
    def handler(request: httpx.Request) -> httpx.Response:
        return spoke('{"name": "auth"}')

    with pytest.raises(Upstream, match="could not produce a Shape"):
        await gemini(handler).structured("go", Shape)


async def test_describe_image_sends_inline_data_alongside_the_prompt():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return spoke("A red square.")

    result = await gemini(handler).describe_image(b"\x89PNG...", "image/png", prompt="What is this?")

    assert result == "A red square."
    parts = seen["body"]["contents"][0]["parts"]
    assert parts[0] == {
        "inlineData": {
            "mimeType": "image/png",
            "data": base64.standard_b64encode(b"\x89PNG...").decode("ascii"),
        }
    }
    assert parts[1] == {"text": "What is this?"}


async def test_an_http_failure_becomes_one_of_our_errors(monkeypatch):
    monkeypatch.setattr(http_client.asyncio, "sleep", _instant)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota exceeded"}})

    with pytest.raises(Upstream, match="quota exceeded"):
        await gemini(handler).text("go")


async def test_a_transient_failure_is_retried_and_can_still_succeed(monkeypatch):
    monkeypatch.setattr(http_client.asyncio, "sleep", _instant)
    replies = iter([httpx.Response(503, text="overloaded"), spoke("ready")])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(replies)

    assert await gemini(handler).text("go") == "ready"


async def test_a_non_transient_failure_is_not_retried(monkeypatch):
    monkeypatch.setattr(http_client.asyncio, "sleep", _instant)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(Upstream, match="bad request"):
        await gemini(handler).text("go")
    assert len(calls) == 1


def test_an_answer_starved_by_thinking_is_a_failure_not_an_empty_string():
    starved = {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}
    with pytest.raises(Upstream, match="MAX_TOKENS"):
        _spoken(starved)


def test_a_blocked_prompt_says_so():
    with pytest.raises(Upstream, match="no candidates"):
        _spoken({"promptFeedback": {"blockReason": "SAFETY"}})


def test_an_unreadable_error_body_still_reports_the_status():
    error = httpx.HTTPStatusError(
        "boom", request=httpx.Request("POST", "https://x"), response=httpx.Response(500, text="<html>")
    )
    assert "HTTP 500" in reason(error)


def openai(handler) -> OpenAIClient:
    """A real client with its transport swapped, so headers and body building are still exercised."""
    client = OpenAIClient(api_key="k", model="m", max_tokens=100, max_concurrency=2, timeout=5.0)
    client._http = httpx.AsyncClient(
        base_url="https://example.invalid",
        headers={"Authorization": "Bearer k"},
        transport=httpx.MockTransport(handler),
    )
    return client


def spoke_openai(text: str, finish: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        },
    )


async def test_openai_text_asks_for_what_it_was_given():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.read())
        seen["auth"] = request.headers.get("authorization")
        return spoke_openai("ready")

    assert await openai(handler).text("say ready", system="be terse") == "ready"
    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "say ready"},
    ]
    assert "response_format" not in seen["body"]


async def test_openai_structured_asks_for_json_and_returns_the_model():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return spoke_openai('{"name": "auth", "count": 3}')

    assert await openai(handler).structured("go", Shape) == Shape(name="auth", count=3)
    assert seen["body"]["response_format"] == {"type": "json_object"}


async def test_openai_a_reply_of_the_wrong_shape_is_asked_for_again():
    replies = iter([spoke_openai('{"name": "auth"}'), spoke_openai('{"name": "auth", "count": 3}')])
    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.read().decode())
        return next(replies)

    assert await openai(handler).structured("go", Shape) == Shape(name="auth", count=3)
    assert len(asked) == 2
    assert "did not match" in asked[1]


async def test_openai_a_reply_that_stays_wrong_fails_rather_than_guessing():
    def handler(request: httpx.Request) -> httpx.Response:
        return spoke_openai('{"name": "auth"}')

    with pytest.raises(Upstream, match="could not produce a Shape"):
        await openai(handler).structured("go", Shape)


async def test_openai_describe_image_sends_a_data_url_alongside_the_prompt():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return spoke_openai("A red square.")

    result = await openai(handler).describe_image(b"\x89PNG...", "image/png", prompt="What is this?")

    assert result == "A red square."
    content = seen["body"]["messages"][0]["content"]
    assert content[0] == {
        "type": "image_url",
        "image_url": {
            "url": "data:image/png;base64," + base64.standard_b64encode(b"\x89PNG...").decode("ascii"),
        },
    }
    assert content[1] == {"type": "text", "text": "What is this?"}


async def test_openai_usage_accumulates():
    client = openai(lambda request: spoke_openai("ok"))
    await client.text("hi")
    assert (client.input_tokens, client.output_tokens) == (3, 2)


async def test_openai_a_transient_failure_is_retried_and_can_still_succeed(monkeypatch):
    monkeypatch.setattr(http_client.asyncio, "sleep", _instant)
    replies = iter([httpx.Response(503, text="overloaded"), spoke_openai("ready")])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(replies)

    assert await openai(handler).text("go") == "ready"


async def test_openai_a_non_transient_failure_is_not_retried(monkeypatch):
    monkeypatch.setattr(http_client.asyncio, "sleep", _instant)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(Upstream, match="bad request"):
        await openai(handler).text("go")
    assert len(calls) == 1


def test_openai_an_empty_reply_is_a_failure_not_an_empty_string():
    with pytest.raises(Upstream, match="nothing"):
        _openai_spoken({"choices": [{"message": {"content": ""}, "finish_reason": "length"}]})


def test_openai_no_choices_says_so():
    with pytest.raises(Upstream, match="no choices"):
        _openai_spoken({"choices": []})
