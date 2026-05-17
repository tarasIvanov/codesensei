"""Index error envelope: category → HTTP code map + exception type."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class IndexErrorCategory(StrEnum):
    INVALID_INPUT = "invalid_input"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    ALREADY_INDEXING = "already_indexing"
    CLONE_FAILED = "clone_failed"
    EMBEDDING_FAILED = "embedding_failed"
    EMBEDDING_DIMENSION_MISMATCH = "embedding_dimension_mismatch"
    EMBEDDING_MISMATCH = "embedding_mismatch"
    DELETE_DURING_INDEX = "delete_during_index"
    QUEUE_UNAVAILABLE = "queue_unavailable"
    NOT_FOUND = "not_found"
    INTERNAL = "internal"


HTTP_FOR_INDEX_CATEGORY: MappingProxyType[IndexErrorCategory, int] = MappingProxyType(
    {
        IndexErrorCategory.INVALID_INPUT: 400,
        IndexErrorCategory.PAYLOAD_TOO_LARGE: 413,
        IndexErrorCategory.ALREADY_INDEXING: 409,
        IndexErrorCategory.CLONE_FAILED: 502,
        IndexErrorCategory.EMBEDDING_FAILED: 502,
        IndexErrorCategory.EMBEDDING_DIMENSION_MISMATCH: 500,
        IndexErrorCategory.EMBEDDING_MISMATCH: 422,
        IndexErrorCategory.DELETE_DURING_INDEX: 409,
        IndexErrorCategory.QUEUE_UNAVAILABLE: 502,
        IndexErrorCategory.NOT_FOUND: 404,
        IndexErrorCategory.INTERNAL: 500,
    }
)


class IndexError(Exception):  # noqa: A001 — distinct from builtin IndexError; namespaced by import
    """Single normalized exception used across the indexing pipeline."""

    def __init__(
        self,
        category: IndexErrorCategory,
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
        return HTTP_FOR_INDEX_CATEGORY[self.category]

    def to_envelope(self) -> dict[str, dict[str, object]]:
        return {
            "error": {
                "category": self.category.value,
                "message": self.message,
                "retryable": self.retryable,
            }
        }
