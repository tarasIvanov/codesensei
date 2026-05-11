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


def classify_http_status(code: int) -> bool:
    """Return True if the upstream HTTP status code is retryable."""
    if 500 <= code < 600:
        return True
    if code in (408, 429):
        return True
    return False
