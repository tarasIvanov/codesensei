"""US3: OpenAI adapter — chat + embed happy paths + error normalization."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from codesensei.config import get_settings
from codesensei.providers import ProviderError
from codesensei.providers.openai_adapter import (
    OpenAIChatProvider,
    OpenAIEmbeddingProvider,
)


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _mock(value):
    if isinstance(value, BaseException):
        return AsyncMock(side_effect=value)
    return AsyncMock(return_value=value)


def _install_fake_openai_client(monkeypatch, *, chat=None, embed=None):
    """Replace `AsyncOpenAI` so the adapter sees AsyncMock surfaces."""
    chat_mock = _mock(chat)
    embed_mock = _mock(embed)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=chat_mock))
            self.embeddings = SimpleNamespace(create=embed_mock)

    monkeypatch.setattr("openai.AsyncOpenAI", FakeClient)
    return chat_mock, embed_mock


def _chat_response(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _embed_response(vectors: list[list[float]]):
    return SimpleNamespace(data=[SimpleNamespace(embedding=v) for v in vectors])


async def test_chat_happy(monkeypatch):
    _install_fake_openai_client(monkeypatch, chat=_chat_response("hello"))
    out = await OpenAIChatProvider().chat([{"role": "user", "content": "hi"}])
    assert out == "hello"


async def test_chat_empty_completion_raises(monkeypatch):
    _install_fake_openai_client(monkeypatch, chat=_chat_response(""))
    with pytest.raises(ProviderError) as exc:
        await OpenAIChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.retryable is False
    assert "empty" in exc.value.message.lower()


async def test_chat_503_retryable(monkeypatch):
    from openai import APIStatusError

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(503, request=request)
    err = APIStatusError("upstream blew up", response=response, body=None)
    _install_fake_openai_client(monkeypatch, chat=err)
    with pytest.raises(ProviderError) as exc:
        await OpenAIChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.provider == "openai"
    assert exc.value.retryable is True


async def test_chat_401_non_retryable(monkeypatch):
    from openai import AuthenticationError

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(401, request=request)
    err = AuthenticationError("bad key", response=response, body=None)
    _install_fake_openai_client(monkeypatch, chat=err)
    with pytest.raises(ProviderError) as exc:
        await OpenAIChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.retryable is False


async def test_chat_rate_limit_retryable(monkeypatch):
    from openai import RateLimitError

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    err = RateLimitError("slow down", response=response, body=None)
    _install_fake_openai_client(monkeypatch, chat=err)
    with pytest.raises(ProviderError) as exc:
        await OpenAIChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.retryable is True


async def test_embed_happy(monkeypatch):
    _install_fake_openai_client(monkeypatch, embed=_embed_response([[0.1, 0.2], [0.3, 0.4]]))
    out = await OpenAIEmbeddingProvider().embed(["a", "b"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_rejects_empty_input():
    with pytest.raises(ProviderError) as exc:
        await OpenAIEmbeddingProvider().embed([])
    assert exc.value.retryable is False


async def test_embed_rate_limit_retryable(monkeypatch):
    from openai import RateLimitError

    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(429, request=request)
    err = RateLimitError("slow down", response=response, body=None)
    _install_fake_openai_client(monkeypatch, embed=err)
    with pytest.raises(ProviderError) as exc:
        await OpenAIEmbeddingProvider().embed(["text"])
    assert exc.value.retryable is True
