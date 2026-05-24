"""POST /api/review router (feature 018: async-only, ADR-019)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from codesensei.config import get_settings
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.schema import ReviewRequest
from codesensei.tasks.enqueue import enqueue_review
from codesensei.tasks.errors import JobError, JobErrorCategory

router = APIRouter(tags=["review"])
_logger = structlog.get_logger()


def _enforce_diff_size(diff: str | None) -> None:
    """Early payload-size guard (defence in depth; the worker re-checks)."""
    if diff is None:
        return
    limit = get_settings().review_max_diff_bytes
    if len(diff.encode("utf-8")) > limit:
        raise ReviewError(
            ReviewErrorCategory.PAYLOAD_TOO_LARGE,
            f"Diff exceeds the {limit // 1000} KB limit. Try a smaller change.",
        )


@router.post("/review", status_code=status.HTTP_202_ACCEPTED)
async def post_review(body: ReviewRequest) -> JSONResponse:
    """Enqueue a review job and return 202 + job_id. Result streams via WS /api/jobs/{id}/stream."""
    _enforce_diff_size(body.diff)

    payload: dict[str, object] = {}
    if body.diff is not None:
        payload["diff"] = body.diff
    if body.pr_url is not None:
        payload["pr_url"] = body.pr_url
    if body.repo_id is not None:
        payload["repo_id"] = str(body.repo_id)

    try:
        job_id = await enqueue_review(payload)
    except JobError as exc:
        if exc.category == JobErrorCategory.QUEUE_UNAVAILABLE:
            raise ReviewError(
                ReviewErrorCategory.PROVIDER_UNAVAILABLE,
                exc.message,
                retryable=True,
            ) from exc
        _logger.warning(
            "review_enqueue_failed",
            category=exc.category.value,
            message=exc.message,
        )
        raise ReviewError(
            ReviewErrorCategory.INTERNAL,
            "Could not enqueue review job.",
        ) from exc
    except (RedisError, OSError) as exc:
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_UNAVAILABLE,
            f"Job queue is unreachable: {exc}",
            retryable=True,
        ) from exc

    _logger.info(
        "review_enqueued",
        job_id=job_id,
        input_kind="pr_url" if body.pr_url is not None else "diff",
        repo_id=str(body.repo_id) if body.repo_id else None,
    )
    return JSONResponse(
        content={"job_id": job_id, "mode": "async"},
        status_code=status.HTTP_202_ACCEPTED,
    )
