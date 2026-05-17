"""US4: provider probes — no paid API calls; correct state for each scenario."""

from __future__ import annotations

import httpx
import pytest

from codesensei.config import get_settings
from codesensei.providers.base import ProviderState
from codesensei.providers.factory import _reset_provider_cache
from codesensei.providers.probe import probe_embedding_provider, probe_llm_provider


@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    _reset_provider_cache()
    yield
    get_settings.cache_clear()
    _reset_provider_cache()


async def test_llm_openai_with_key_is_ok(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    get_settings.cache_clear()
    _reset_provider_cache()
    result = await probe_llm_provider()
    assert result.state is ProviderState.OK
    assert result.provider == "openai"


async def test_llm_openai_without_key_is_unconfigured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    _reset_provider_cache()
    result = await probe_llm_provider()
    assert result.state is ProviderState.UNCONFIGURED


async def test_llm_anthropic_with_key_is_ok(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    get_settings.cache_clear()
    _reset_provider_cache()
    result = await probe_llm_provider()
    assert result.state is ProviderState.OK
    assert result.provider == "anthropic"


async def test_llm_anthropic_without_key_is_unconfigured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    _reset_provider_cache()
    result = await probe_llm_provider()
    assert result.state is ProviderState.UNCONFIGURED


async def test_llm_ollama_reachable_is_ok(monkeypatch, _respx_block_unintercepted_http):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    get_settings.cache_clear()
    _reset_provider_cache()
    _respx_block_unintercepted_http.get("http://ollama:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    result = await probe_llm_provider()
    assert result.state is ProviderState.OK


async def test_llm_ollama_connect_error_is_unreachable(
    monkeypatch, _respx_block_unintercepted_http
):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    get_settings.cache_clear()
    _reset_provider_cache()
    _respx_block_unintercepted_http.get("http://ollama:11434/api/tags").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = await probe_llm_provider()
    assert result.state is ProviderState.UNREACHABLE


async def test_llm_ollama_500_is_unreachable(monkeypatch, _respx_block_unintercepted_http):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    get_settings.cache_clear()
    _reset_provider_cache()
    _respx_block_unintercepted_http.get("http://ollama:11434/api/tags").mock(
        return_value=httpx.Response(500)
    )
    result = await probe_llm_provider()
    assert result.state is ProviderState.UNREACHABLE


async def test_embedding_anthropic_misconfig_is_unconfigured(monkeypatch):
    """Factory rejects Anthropic-as-embedding; probe surfaces unconfigured, doesn't crash."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "anthropic")
    get_settings.cache_clear()
    _reset_provider_cache()
    result = await probe_embedding_provider()
    assert result.state is ProviderState.UNCONFIGURED


async def test_embedding_ollama_unreachable(monkeypatch, _respx_block_unintercepted_http):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    get_settings.cache_clear()
    _reset_provider_cache()
    _respx_block_unintercepted_http.get("http://ollama:11434/api/tags").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = await probe_embedding_provider()
    assert result.state is ProviderState.UNREACHABLE
