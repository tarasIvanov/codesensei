"""Normalized provider exception + HTTP-status classification (contracts/provider_error.md)."""

from __future__ import annotations


class ProviderError(Exception):
    def __init__(self, provider: str, message: str, *, retryable: bool) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message
        self.retryable = retryable

    def __str__(self) -> str:
        return f"{self.provider}: {self.message}"


def classify_http_status(provider: str, code: int) -> bool:
    """Return True if the upstream HTTP status code is retryable for the given provider.

    Different providers expose different retry semantics:
      * Ollama is a local runtime — no rate limits, no 408/429.
      * Anthropic uses 529 ("overloaded") in addition to 429.
      * Default (OpenAI-compatible) treats 5xx + 408/429 as retryable.
    """
    if provider == "ollama":
        return 500 <= code < 600
    if provider == "anthropic":
        return 500 <= code < 600 or code in (429, 529)
    if 500 <= code < 600:
        return True
    return code in (408, 429)
