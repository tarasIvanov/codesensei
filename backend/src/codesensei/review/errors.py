"""Review error envelope: category → HTTP code map + exception type."""
from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class ReviewErrorCategory(StrEnum):
    INVALID_INPUT = "invalid_input"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    GITHUB_FETCH_FAILED = "github_fetch_failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_MALFORMED_OUTPUT = "provider_malformed_output"
    SETTINGS_LOCKED = "settings_locked"
    INTERNAL = "internal"


HTTP_FOR_CATEGORY: MappingProxyType[ReviewErrorCategory, int] = MappingProxyType(
    {
        ReviewErrorCategory.INVALID_INPUT: 400,
        ReviewErrorCategory.PAYLOAD_TOO_LARGE: 413,
        ReviewErrorCategory.GITHUB_FETCH_FAILED: 502,
        ReviewErrorCategory.PROVIDER_UNAVAILABLE: 502,
        ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT: 502,
        ReviewErrorCategory.SETTINGS_LOCKED: 503,
        ReviewErrorCategory.INTERNAL: 500,
    }
)


class ReviewError(Exception):
    """Single normalized exception used across the review pipeline."""

    def __init__(
        self,
        category: ReviewErrorCategory,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(f"{category.value}: {message}")
        self.category = category
        self.message = message
        self.retryable = retryable

    @property
    def http_status(self) -> int:
        return HTTP_FOR_CATEGORY[self.category]

    def to_envelope(self) -> dict[str, dict[str, object]]:
        return {
            "error": {
                "category": self.category.value,
                "message": self.message,
                "retryable": self.retryable,
            }
        }
