"""US1+US2: provider factory selection + Anthropic-embedding rejection."""
from __future__ import annotations

import pytest

from codesensei.config import get_settings
from codesensei.providers import (
    EmbeddingProvider,
    LLMProvider,
    ProviderError,
    get_embedding_provider,
    get_llm_provider,
)
from codesensei.providers.factory import _reset_provider_cache


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    get_settings.cache_clear()
    _reset_provider_cache()
    yield
    get_settings.cache_clear()
    _reset_provider_cache()


@pytest.mark.parametrize(
    "value,expected_module",
    [
        ("openai", "openai_adapter"),
        ("OPENAI", "openai_adapter"),
        ("  openai  ", "openai_adapter"),
        ("anthropic", "anthropic_adapter"),
        ("Anthropic", "anthropic_adapter"),
        ("ollama", "ollama_adapter"),
    ],
)
def test_llm_factory_returns_expected_adapter(monkeypatch, value, expected_module):
    monkeypatch.setenv("LLM_PROVIDER", value)
    get_settings.cache_clear()
    _reset_provider_cache()
    provider = get_llm_provider()
    assert isinstance(provider, LLMProvider)
    assert expected_module in type(provider).__module__


@pytest.mark.parametrize(
    "value,expected_module",
    [
        ("openai", "openai_adapter"),
        ("OPENAI", "openai_adapter"),
        ("  openai  ", "openai_adapter"),
        ("ollama", "ollama_adapter"),
        ("Ollama", "ollama_adapter"),
    ],
)
def test_embedding_factory_returns_expected_adapter(monkeypatch, value, expected_module):
    monkeypatch.setenv("EMBEDDING_PROVIDER", value)
    get_settings.cache_clear()
    _reset_provider_cache()
    provider = get_embedding_provider()
    assert isinstance(provider, EmbeddingProvider)
    assert expected_module in type(provider).__module__


def test_llm_factory_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    get_settings.cache_clear()
    _reset_provider_cache()
    with pytest.raises(ProviderError) as exc:
        get_llm_provider()
    assert exc.value.provider == "config"
    assert exc.value.retryable is False
    msg = exc.value.message
    assert "mistral" in msg
    for accepted in ("openai", "anthropic", "ollama"):
        assert accepted in msg


def test_embedding_factory_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "cohere")
    get_settings.cache_clear()
    _reset_provider_cache()
    with pytest.raises(ProviderError) as exc:
        get_embedding_provider()
    assert exc.value.provider == "config"
    assert exc.value.retryable is False
    msg = exc.value.message
    assert "cohere" in msg
    for accepted in ("openai", "ollama"):
        assert accepted in msg


def test_embedding_anthropic_rejected(monkeypatch):
    """US2: EMBEDDING_PROVIDER=anthropic must surface a dedicated message."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "anthropic")
    get_settings.cache_clear()
    _reset_provider_cache()
    with pytest.raises(ProviderError) as exc:
        get_embedding_provider()
    assert exc.value.provider == "config"
    assert exc.value.retryable is False
    msg = exc.value.message
    assert "EMBEDDING_PROVIDER" in msg
    assert "anthropic" in msg
    assert "openai" in msg
    assert "ollama" in msg


async def test_runtime_apply_overrides_env_with_stored_value(monkeypatch):
    """US2: stored LLM_PROVIDER in app_settings beats the env baseline at the next factory call."""
    import os

    from codesensei.providers.factory import get_llm_provider
    from codesensei.settings_store import runtime, store

    # Snapshot env we'll touch via direct os.environ mutation in runtime layer.
    saved_env = {k: os.environ.get(k) for k in store.WHITELIST}
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    _reset_provider_cache()

    async def fake_get_effective():
        return {k: None for k in store.WHITELIST} | {"LLM_PROVIDER": "anthropic"}

    monkeypatch.setattr(
        "codesensei.settings_store.runtime.get_effective_settings", fake_get_effective
    )
    runtime._snapshot_taken = False
    runtime._baseline.clear()
    try:
        await runtime.apply_store_overrides_to_env()
        provider = get_llm_provider()
        assert provider.name == "anthropic"
    finally:
        # Restore env exactly to its pre-test state.
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        runtime._snapshot_taken = False
        runtime._baseline.clear()
        get_settings.cache_clear()
        _reset_provider_cache()


def test_package_import_does_not_touch_network(monkeypatch):
    """FR-005: importing codesensei.providers must not instantiate any HTTP client."""
    import httpx

    def boom(*args, **kwargs):
        raise AssertionError("network touched during import")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", boom)

    # Re-import to ensure the no-network rule still holds (cached or fresh).
    import importlib

    import codesensei.providers as pkg

    importlib.reload(pkg)
