"""Error envelope for /api/jobs/* (shape mirrors review.errors)."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class JobErrorCategory(StrEnum):
    INVALID_INPUT = "invalid_input"
    QUEUE_UNAVAILABLE = "queue_unavailable"
    NOT_FOUND = "not_found"
    INTERNAL = "internal"


HTTP_FOR_CATEGORY: MappingProxyType[JobErrorCategory, int] = MappingProxyType(
    {
        JobErrorCategory.INVALID_INPUT: 400,
        JobErrorCategory.QUEUE_UNAVAILABLE: 502,
        JobErrorCategory.NOT_FOUND: 404,
        JobErrorCategory.INTERNAL: 500,
    }
)


class JobError(Exception):
    def __init__(
        self,
        category: JobErrorCategory,
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
