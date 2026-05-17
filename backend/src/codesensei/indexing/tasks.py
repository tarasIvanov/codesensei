"""arq job — index a repository in the background (long-running)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from codesensei.indexing.errors import IndexError
from codesensei.indexing.service import IndexingService

_logger = structlog.get_logger()


async def index_repo_job(
    ctx: dict[str, Any],  # noqa: ARG001 — arq passes ctx; unused
    repo_id: str,
    source: str,  # noqa: ARG001 — kept for future signature parity / observability
    source_kind: str,  # noqa: ARG001
    default_branch: str | None,  # noqa: ARG001
) -> dict[str, Any]:
    """arq entry point. Returns the success or failure envelope per contract."""
    rid = UUID(repo_id)
    service = IndexingService.from_request()
    try:
        return await service.run_for_existing_repo(rid)
    except IndexError as exc:
        _logger.warning(
            "index_repo_job.failed",
            repo_id=repo_id,
            category=exc.category.value,
            message=exc.message,
        )
        return {
            "repo_id": str(rid),
            "error": {
                "category": exc.category.value,
                "message": exc.message,
                "retryable": exc.retryable,
            },
        }
