"""Anthropic adapter — chat only (Messages API). No embedding implementation."""
from __future__ import annotations

from typing import TYPE_CHECKING

from codesensei.config import get_settings
from codesensei.providers.base import ChatMessage
from codesensei.providers.errors import ProviderError, classify_http_status

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

DEFAULT_CHAT_MODEL = "claude-3-5-sonnet-latest"


def _client() -> AsyncAnthropic:
    from anthropic import AsyncAnthropic

    settings = get_settings()
    return AsyncAnthropic(api_key=settings.anthropic_api_key or None)


def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
    """Anthropic Messages API expects a top-level `system` string, not a role entry."""
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]
    system = "\n\n".join(system_parts) if system_parts else None
    return system, rest


def _translate(exc: Exception) -> ProviderError:
    from anthropic import (
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
        return ProviderError("anthropic", str(exc), retryable=False)
    if isinstance(exc, (BadRequestError, NotFoundError, PermissionDeniedError)):
        return ProviderError("anthropic", str(exc), retryable=False)
    if isinstance(exc, RateLimitError):
        return ProviderError("anthropic", str(exc), retryable=True)
    if isinstance(exc, APITimeoutError):
        return ProviderError("anthropic", str(exc), retryable=True)
    if isinstance(exc, APIConnectionError):
        return ProviderError("anthropic", str(exc), retryable=True)
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", 0) or 0
        return ProviderError("anthropic", str(exc), retryable=classify_http_status(code))
    return ProviderError("anthropic", str(exc), retryable=False)


class AnthropicChatProvider:
    name = "anthropic"

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        chosen = model or get_settings().llm_model or DEFAULT_CHAT_MODEL
        system, rest = _split_system(messages)
        kwargs: dict = {
            "model": chosen,
            "messages": [{"role": m["role"], "content": m["content"]} for m in rest],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system is not None:
            kwargs["system"] = system
        try:
            response = await _client().messages.create(**kwargs)
        except Exception as exc:
            raise _translate(exc) from exc

        blocks = getattr(response, "content", [])
        text = next(
            (getattr(b, "text", "") for b in blocks if getattr(b, "type", "") == "text"),
            "",
        )
        if not text:
            raise ProviderError("anthropic", "empty completion", retryable=False)
        return text
