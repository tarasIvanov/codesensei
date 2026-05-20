"""Provider adapter `_last_usage` population tests (feature 012)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from codesensei.config import get_settings
from codesensei.providers import ProviderError
from codesensei.providers.anthropic_adapter import AnthropicChatProvider
from codesensei.providers.base import ChatUsage
from codesensei.providers.ollama_adapter import OllamaChatProvider
from codesensei.providers.openai_adapter import OpenAIChatProvider

OLLAMA_BASE = "http://ollama:11434"


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------- OpenAI ----------


def _install_openai(monkeypatch, *, chat=None):
    if isinstance(chat, BaseException):
        chat_mock = AsyncMock(side_effect=chat)
    else:
        chat_mock = AsyncMock(return_value=chat)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=chat_mock))
            self.embeddings = SimpleNamespace(create=AsyncMock())

    monkeypatch.setattr("openai.AsyncOpenAI", FakeClient)


async def test_openai_populates_last_usage(monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))],
        usage=SimpleNamespace(prompt_tokens=42, completion_tokens=17),
        model="gpt-4o-mini-2024-07-18",
    )
    _install_openai(monkeypatch, chat=response)
    provider = OpenAIChatProvider()
    assert provider._last_usage is None
    await provider.chat([{"role": "user", "content": "hi"}])
    assert isinstance(provider._last_usage, ChatUsage)
    assert provider._last_usage.prompt_tokens == 42
    assert provider._last_usage.completion_tokens == 17
    assert provider._last_usage.model == "gpt-4o-mini-2024-07-18"


async def test_openai_exception_leaves_last_usage_none(monkeypatch):
    from openai import APIStatusError

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(503, request=request)
    err = APIStatusError("boom", response=response, body=None)
    _install_openai(monkeypatch, chat=err)
    provider = OpenAIChatProvider()
    with pytest.raises(ProviderError):
        await provider.chat([{"role": "user", "content": "hi"}])
    assert provider._last_usage is None


# ---------- Anthropic ----------


def _install_anthropic(monkeypatch, *, response=None, side_effect=None):
    if side_effect is not None:
        create = AsyncMock(side_effect=side_effect)
    else:
        create = AsyncMock(return_value=response)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = SimpleNamespace(create=create)

    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeClient)


async def test_anthropic_populates_last_usage(monkeypatch):
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hi")],
        usage=SimpleNamespace(input_tokens=123, output_tokens=45),
    )
    _install_anthropic(monkeypatch, response=response)
    provider = AnthropicChatProvider()
    await provider.chat(
        [{"role": "user", "content": "hi"}],
        model="claude-3-5-sonnet-latest",
    )
    assert isinstance(provider._last_usage, ChatUsage)
    assert provider._last_usage.prompt_tokens == 123
    assert provider._last_usage.completion_tokens == 45
    assert provider._last_usage.model == "claude-3-5-sonnet-latest"


async def test_anthropic_exception_leaves_last_usage_none(monkeypatch):
    from anthropic import APIStatusError

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(503, request=request)
    err = APIStatusError(
        message="overloaded", response=response, body={"error": {"message": "down"}}
    )
    _install_anthropic(monkeypatch, side_effect=err)
    provider = AnthropicChatProvider()
    with pytest.raises(ProviderError):
        await provider.chat([{"role": "user", "content": "hi"}])
    assert provider._last_usage is None


# ---------- Ollama ----------


async def test_ollama_populates_last_usage_when_fields_present(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{OLLAMA_BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"content": "hi"},
                "prompt_eval_count": 88,
                "eval_count": 22,
            },
        )
    )
    provider = OllamaChatProvider()
    await provider.chat([{"role": "user", "content": "hi"}], model="llama3.1:8b")
    assert isinstance(provider._last_usage, ChatUsage)
    assert provider._last_usage.prompt_tokens == 88
    assert provider._last_usage.completion_tokens == 22
    assert provider._last_usage.model == "llama3.1:8b"


async def test_ollama_no_usage_keeps_last_usage_none(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{OLLAMA_BASE}/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "hi"}})
    )
    provider = OllamaChatProvider()
    await provider.chat([{"role": "user", "content": "hi"}])
    assert provider._last_usage is None


async def test_ollama_only_one_field_keeps_last_usage_none(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{OLLAMA_BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": "hi"}, "prompt_eval_count": 88},
        )
    )
    provider = OllamaChatProvider()
    await provider.chat([{"role": "user", "content": "hi"}])
    assert provider._last_usage is None


async def test_ollama_exception_leaves_last_usage_none(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{OLLAMA_BASE}/api/chat").mock(
        side_effect=httpx.ConnectError("refused")
    )
    provider = OllamaChatProvider()
    with pytest.raises(ProviderError):
        await provider.chat([{"role": "user", "content": "hi"}])
    assert provider._last_usage is None
