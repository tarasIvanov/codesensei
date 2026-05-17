"""POST /api/review router."""
from __future__ import annotations

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.schema import ReviewRequest
from codesensei.review.service import ReviewService

router = APIRouter(tags=["review"])
_logger = structlog.get_logger()


@router.post("/review")
async def post_review(body: ReviewRequest) -> JSONResponse:
    service = ReviewService()
    payload_bytes = len((body.diff or "").encode("utf-8")) if body.diff else None
    try:
        if body.diff is not None:
            result = await service.run_for_diff(body.diff, repo_id=body.repo_id)
        else:
            assert body.pr_url is not None
            result = await service.run_for_url(body.pr_url, repo_id=body.repo_id)
    except ReviewError as exc:
        _logger.warning(
            "review.failed",
            error_category=exc.category.value,
            retryable=exc.retryable,
            payload_bytes=payload_bytes,
        )
        raise
    except Exception:
        _logger.exception("review.failed", error_category="internal")
        raise ReviewError(
            ReviewErrorCategory.INTERNAL, "Unexpected server error."
        ) from None
    _logger.info(
        "review.completed",
        provider=result.provider,
        payload_bytes=payload_bytes,
        finding_count=len(result.findings),
        elapsed_ms=result.elapsed_ms,
        repo_id=str(body.repo_id) if body.repo_id else None,
    )
    # Omit `context_files` from the JSON if it is None — keeps 003/004 byte-equivalence.
    body_dict = result.model_dump(exclude_none=False)
    if result.context_files is None:
        body_dict.pop("context_files", None)
    return JSONResponse(content=body_dict)
