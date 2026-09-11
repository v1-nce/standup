import asyncio
import base64
import types

import anthropic
import pytest
from pydantic import BaseModel

from standup.core.llm import LLMClient
from standup.core.llm.anthropic_client import MAX_RETRIES, _translated
from standup.errors import NotConfigured, Upstream


class Out(BaseModel):
    value: str


def make_client(**overrides) -> LLMClient:
    kwargs = {"api_key": "k", "model": "m", "max_tokens": 100, "max_concurrency": 2, "timeout": 1.0}
    kwargs.update(overrides)
    return LLMClient(**kwargs)


def text_block(text: str):
    return types.SimpleNamespace(type="text", text=text)


def usage(input_tokens: int = 1, output_tokens: int = 1):
    return types.SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def attach(client: LLMClient, response) -> FakeMessages:
    fake = FakeMessages(response)
    client._client = types.SimpleNamespace(messages=fake)
    return fake


def test_missing_key_raises():
    with pytest.raises(NotConfigured):
        make_client(api_key="")


def test_the_retry_count_is_explicit_not_left_to_the_sdks_own_default():
    """Gemini's own retry loop assumes this matches — pin it so an SDK default change can't
    silently break that assumption."""
    client = make_client()
    assert client._client.max_retries == MAX_RETRIES


def test_provider_errors_do_not_escape():
    with pytest.raises(Upstream), _translated():
        raise anthropic.APIConnectionError(request=None)


async def test_text_joins_only_text_blocks():
    client = make_client()
    attach(
        client,
        types.SimpleNamespace(
            content=[text_block("a"), types.SimpleNamespace(type="thinking"), text_block("b")],
            usage=usage(),
        ),
    )
    assert await client.text("hi") == "ab"


async def test_an_answer_starved_by_thinking_is_a_failure_not_an_empty_string():
    client = make_client()
    attach(
        client,
        types.SimpleNamespace(
            content=[types.SimpleNamespace(type="thinking")], stop_reason="max_tokens", usage=usage()
        ),
    )
    with pytest.raises(Upstream, match="max_tokens"):
        await client.text("hi")


async def test_system_omitted_unless_given():
    client = make_client()
    fake = attach(client, types.SimpleNamespace(content=[text_block("ok")], usage=usage()))
    await client.text("hi")
    assert "system" not in fake.calls[0]
    assert fake.calls[0]["max_tokens"] == 100
    assert fake.calls[0]["messages"] == [{"role": "user", "content": "hi"}]


async def test_system_and_max_tokens_passed_through():
    client = make_client()
    fake = attach(client, types.SimpleNamespace(content=[text_block("ok")], usage=usage()))
    await client.text("hi", system="s", max_tokens=7)
    assert fake.calls[0]["system"] == [
        {"type": "text", "text": "s", "cache_control": {"type": "ephemeral"}}
    ]
    assert fake.calls[0]["max_tokens"] == 7


async def test_structured_returns_parsed_output():
    client = make_client()
    fake = attach(client, types.SimpleNamespace(parsed_output=Out(value="x"), usage=usage()))
    result = await client.structured("hi", Out)
    assert result.value == "x"
    assert fake.calls[0]["output_format"] is Out


async def test_usage_accumulates_across_calls():
    client = make_client()
    attach(client, types.SimpleNamespace(content=[text_block("ok")], usage=usage(3, 5)))
    await client.text("hi")
    await client.text("hi again")
    assert (client.input_tokens, client.output_tokens) == (6, 10)


async def test_describe_image_sends_the_bytes_as_a_base64_block():
    client = make_client()
    fake = attach(client, types.SimpleNamespace(content=[text_block("A red square.")], usage=usage()))

    result = await client.describe_image(b"\x89PNG...", "image/png", prompt="What is this?")

    assert result == "A red square."
    content = fake.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.standard_b64encode(b"\x89PNG...").decode("ascii"),
    }
    assert content[1] == {"type": "text", "text": "What is this?"}


async def test_concurrency_is_bounded():
    client = make_client(max_concurrency=2)
    live = peak = 0

    class Slow:
        async def create(self, **kwargs):
            nonlocal live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.01)
            live -= 1
            return types.SimpleNamespace(content=[text_block("ok")], usage=usage())

    client._client = types.SimpleNamespace(messages=Slow())
    await asyncio.gather(*(client.text("x") for _ in range(6)))
    assert peak == 2
