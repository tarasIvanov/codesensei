"""Config-driven provider factories (lazy, lru_cache-keyed, no network on import)."""

from __future__ import annotations

from functools import lru_cache

from codesensei.config import get_settings
from codesensei.providers.base import EmbeddingProvider, LLMProvider
from codesensei.providers.errors import ProviderError

LLM_ACCEPTED = ("openai", "anthropic", "ollama")
EMBEDDING_ACCEPTED = ("openai", "ollama")


def _normalize(value: str) -> str:
    return value.strip().lower()


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    value = _normalize(get_settings().llm_provider)
    if value == "openai":
        from codesensei.providers.openai_adapter import OpenAIChatProvider

        return OpenAIChatProvider()
    if value == "anthropic":
        from codesensei.providers.anthropic_adapter import AnthropicChatProvider

        return AnthropicChatProvider()
    if value == "ollama":
        from codesensei.providers.ollama_adapter import OllamaChatProvider

        return OllamaChatProvider()
    raise ProviderError(
        "config",
        f"LLM_PROVIDER={value!r} is not supported; accepted values: {', '.join(LLM_ACCEPTED)}",
        retryable=False,
    )


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    value = _normalize(get_settings().embedding_provider)
    if value == "openai":
        from codesensei.providers.openai_adapter import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider()
    if value == "ollama":
        from codesensei.providers.ollama_adapter import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider()
    if value == "anthropic":
        raise ProviderError(
            "config",
            (
                "EMBEDDING_PROVIDER=anthropic is not supported because Anthropic "
                "has no embeddings API; accepted values: "
                f"{', '.join(EMBEDDING_ACCEPTED)}"
            ),
            retryable=False,
        )
    raise ProviderError(
        "config",
        f"EMBEDDING_PROVIDER={value!r} is not supported; accepted values: "
        f"{', '.join(EMBEDDING_ACCEPTED)}",
        retryable=False,
    )


def _reset_provider_cache() -> None:
    """Test helper — clear factory caches between tests touching env vars."""
    get_llm_provider.cache_clear()
    get_embedding_provider.cache_clear()
