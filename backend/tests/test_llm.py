import asyncio
import types

import anthropic
import pytest
from pydantic import BaseModel

from errors import NotConfigured, Upstream
from llm import LLMClient
from llm.client import _translated


class Out(BaseModel):
    value: str


def make_client(**overrides) -> LLMClient:
    kwargs = {"api_key": "k", "model": "m", "max_tokens": 100, "max_concurrency": 2, "timeout": 1.0}
    kwargs.update(overrides)
    return LLMClient(**kwargs)


def text_block(text: str):
    return types.SimpleNamespace(type="text", text=text)


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


def test_provider_errors_do_not_escape():
    with pytest.raises(Upstream), _translated():
        raise anthropic.APIConnectionError(request=None)


async def test_text_joins_only_text_blocks():
    client = make_client()
    attach(
        client,
        types.SimpleNamespace(
            content=[text_block("a"), types.SimpleNamespace(type="thinking"), text_block("b")]
        ),
    )
    assert await client.text("hi") == "ab"


async def test_system_omitted_unless_given():
    client = make_client()
    fake = attach(client, types.SimpleNamespace(content=[text_block("ok")]))
    await client.text("hi")
    assert "system" not in fake.calls[0]
    assert fake.calls[0]["max_tokens"] == 100
    assert fake.calls[0]["messages"] == [{"role": "user", "content": "hi"}]


async def test_system_and_max_tokens_passed_through():
    client = make_client()
    fake = attach(client, types.SimpleNamespace(content=[text_block("ok")]))
    await client.text("hi", system="s", max_tokens=7)
    assert fake.calls[0]["system"] == "s"
    assert fake.calls[0]["max_tokens"] == 7


async def test_structured_returns_parsed_output():
    client = make_client()
    fake = attach(client, types.SimpleNamespace(parsed_output=Out(value="x")))
    result = await client.structured("hi", Out)
    assert result.value == "x"
    assert fake.calls[0]["output_format"] is Out


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
            return types.SimpleNamespace(content=[text_block("ok")])

    client._client = types.SimpleNamespace(messages=Slow())
    await asyncio.gather(*(client.text("x") for _ in range(6)))
    assert peak == 2
