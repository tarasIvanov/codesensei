"""US3: Ollama adapter — chat + embed paths via respx-mocked HTTP."""

from __future__ import annotations

import httpx
import pytest

from codesensei.config import get_settings
from codesensei.providers import ProviderError
from codesensei.providers.ollama_adapter import (
    OllamaChatProvider,
    OllamaEmbeddingProvider,
)


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


BASE = "http://ollama:11434"


async def test_chat_happy(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "hello from llama"}})
    )
    out = await OllamaChatProvider().chat([{"role": "user", "content": "hi"}])
    assert out == "hello from llama"


async def test_chat_connect_error_retryable(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{BASE}/api/chat").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(ProviderError) as exc:
        await OllamaChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.provider == "ollama"
    assert exc.value.retryable is True


async def test_chat_500_retryable(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with pytest.raises(ProviderError) as exc:
        await OllamaChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.retryable is True


async def test_chat_404_non_retryable(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(404, text="no model")
    )
    with pytest.raises(ProviderError) as exc:
        await OllamaChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.retryable is False


async def test_chat_empty_completion_raises(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": ""}})
    )
    with pytest.raises(ProviderError) as exc:
        await OllamaChatProvider().chat([{"role": "user", "content": "hi"}])
    assert exc.value.retryable is False


async def test_embed_happy(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{BASE}/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})
    )
    out = await OllamaEmbeddingProvider().embed(["one", "two"])
    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]


async def test_embed_rejects_empty_input():
    with pytest.raises(ProviderError) as exc:
        await OllamaEmbeddingProvider().embed([])
    assert exc.value.retryable is False


async def test_embed_timeout_retryable(_respx_block_unintercepted_http):
    _respx_block_unintercepted_http.post(f"{BASE}/api/embeddings").mock(
        side_effect=httpx.ReadTimeout("slow")
    )
    with pytest.raises(ProviderError) as exc:
        await OllamaEmbeddingProvider().embed(["x"])
    assert exc.value.retryable is True
