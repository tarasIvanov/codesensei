"""OpenAI adapter — chat + embeddings via the official openai SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

from codesensei.config import get_settings
from codesensei.providers.base import ChatMessage, ChatUsage
from codesensei.providers.errors import ProviderError, classify_http_status

if TYPE_CHECKING:
    from openai import AsyncOpenAI

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"


def _client() -> AsyncOpenAI:
    from openai import AsyncOpenAI

    settings = get_settings()
    return AsyncOpenAI(api_key=settings.openai_api_key or None)


def _translate(exc: Exception) -> ProviderError:
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        NotFoundError,
        PermissionDeniedError,
        RateLimitError,
    )

    if isinstance(exc, AuthenticationError):
        return ProviderError("openai", str(exc), retryable=False)
    if isinstance(exc, (BadRequestError, NotFoundError, PermissionDeniedError)):
        return ProviderError("openai", str(exc), retryable=False)
    if isinstance(exc, RateLimitError):
        return ProviderError("openai", str(exc), retryable=True)
    if isinstance(exc, APITimeoutError):
        return ProviderError("openai", str(exc), retryable=True)
    if isinstance(exc, APIConnectionError):
        return ProviderError("openai", str(exc), retryable=True)
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", 0) or 0
        return ProviderError("openai", str(exc), retryable=classify_http_status(code))
    return ProviderError("openai", str(exc), retryable=False)


class OpenAIChatProvider:
    name = "openai"

    def __init__(self) -> None:
        self._last_usage: ChatUsage | None = None

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        chosen = model or get_settings().llm_model or DEFAULT_CHAT_MODEL
        try:
            response = await _client().chat.completions.create(
                model=chosen,
                messages=list(messages),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:  # SDK exception → ProviderError
            raise _translate(exc) from exc

        usage = getattr(response, "usage", None)
        if usage is not None:
            self._last_usage = ChatUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                model=getattr(response, "model", None) or chosen,
            )

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ProviderError("openai", "empty completion", retryable=False)
        return content


class OpenAIEmbeddingProvider:
    name = "openai"

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        if not texts or any(not t for t in texts):
            raise ProviderError("openai", "empty input", retryable=False)
        chosen = model or get_settings().embedding_model or DEFAULT_EMBED_MODEL
        try:
            response = await _client().embeddings.create(model=chosen, input=texts)
        except Exception as exc:
            raise _translate(exc) from exc
        return [d.embedding for d in response.data]
