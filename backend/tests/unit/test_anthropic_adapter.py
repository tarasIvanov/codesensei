"""US3: Anthropic adapter — chat happy path + error normalization."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from codesensei.config import get_settings
from codesensei.providers import ProviderError
from codesensei.providers.anthropic_adapter import AnthropicChatProvider


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _install_fake_anthropic_client(monkeypatch, *, side_effect=None, response=None):
    if side_effect is not None:
        messages_create = AsyncMock(side_effect=side_effect)
    else:
        messages_create = AsyncMock(return_value=response)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = SimpleNamespace(create=messages_create)

    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeClient)
    return messages_create


def _chat_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


async def test_chat_happy(monkeypatch):
    _install_fake_anthropic_client(monkeypatch, response=_chat_response("hi from claude"))
    out = await AnthropicChatProvider().chat(
        [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hello"},
        ]
    )
    assert out == "hi from claude"


async def test_chat_strips_system_from_messages(monkeypatch):
    create_mock = _install_fake_anthropic_client(monkeypatch, response=_chat_response("ok"))
    await AnthropicChatProvider().chat(
        [
            {"role": "system", "content": "S1"},
            {"role": "system", "content": "S2"},
            {"role": "user", "content": "Q"},
        ]
    )
    kwargs = create_mock.call_args.kwargs
    assert "system" in kwargs and "S1" in kwargs["system"] and "S2" in kwargs["system"]
    roles = [m["role"] for m in kwargs["messages"]]
    assert "system" not in roles


async def test_chat_401_non_retryable(monkeypatch):
    from anthropic import AuthenticationError

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(401, request=request)
    err = AuthenticationError(
        message="invalid_api_key", response=response, body={"error": {"message": "bad"}}
    )
    _install_fake_anthropic_client(monkeypatch, side_effect=err)
    with pytest.raises(ProviderError) as exc:
        await AnthropicChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.provider == "anthropic"
    assert exc.value.retryable is False


async def test_chat_503_retryable(monkeypatch):
    from anthropic import APIStatusError

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(503, request=request)
    err = APIStatusError(
        message="overloaded", response=response, body={"error": {"message": "down"}}
    )
    _install_fake_anthropic_client(monkeypatch, side_effect=err)
    with pytest.raises(ProviderError) as exc:
        await AnthropicChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.retryable is True


async def test_chat_empty_completion_raises(monkeypatch):
    _install_fake_anthropic_client(monkeypatch, response=SimpleNamespace(content=[]))
    with pytest.raises(ProviderError) as exc:
        await AnthropicChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.retryable is False
    assert "empty" in exc.value.message.lower()


def test_anthropic_module_has_no_embed_class():
    """FR-009 contract: no embedding implementation lives in the Anthropic module."""
    from codesensei.providers import anthropic_adapter

    assert not hasattr(anthropic_adapter, "AnthropicEmbeddingProvider")
