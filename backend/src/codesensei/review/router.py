"""POST /api/review router."""
from __future__ import annotations

import structlog
from fastapi import APIRouter

from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.schema import ReviewRequest, ReviewResult
from codesensei.review.service import ReviewService

router = APIRouter(tags=["review"])
_logger = structlog.get_logger()


@router.post("/review", response_model=ReviewResult)
async def post_review(body: ReviewRequest) -> ReviewResult:
    service = ReviewService()
    payload_bytes = len((body.diff or "").encode("utf-8")) if body.diff else None
    try:
        if body.diff is not None:
            result = await service.run_for_diff(body.diff)
        else:
            assert body.pr_url is not None
            result = await service.run_for_url(body.pr_url)
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
    )
    return result
