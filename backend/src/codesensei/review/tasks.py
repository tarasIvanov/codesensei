"""arq job — run a code review in the background (feature 018, ADR-019).

Publishes stage progress frames on the Redis pub/sub channel from feature 013, so
the `/api/jobs/{job_id}/stream` WebSocket can stream coarse pipeline stages to the
SPA. The actual review pipeline lives in `review.service._run_chat`; this module
is the queue-facing wrapper.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from codesensei.jobs_stream import publisher as stream_publisher
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.service import ReviewService

_logger = structlog.get_logger(__name__)


async def review_job(
    ctx: dict[str, Any],
    body: dict[str, Any],
) -> dict[str, Any]:
    """arq entry point. Returns success/failure envelope; publishes WS frames.

    `body` is a JSON-serialisable dict carrying the same fields the HTTP request
    validated: {"diff"?, "pr_url"?, "repo_id"?}. Exactly one of diff/pr_url is set.
    """
    job_id = ctx.get("job_id")
    redis_client = ctx.get("redis")

    async def _publish(frame: dict[str, Any]) -> None:
        if job_id is None or redis_client is None:
            return
        try:
            await stream_publisher.publish(redis_client, str(job_id), frame)
        except Exception as exc:  # noqa: BLE001 — best-effort transport
            _logger.warning("review_stream_publish_failed", job_id=str(job_id), error=str(exc))

    async def _on_stage(stage: str, message: str) -> None:
        await _publish({"kind": "progress", "stage": stage, "message": message})

    diff_in: str | None = body.get("diff") if isinstance(body.get("diff"), str) else None
    pr_url: str | None = body.get("pr_url") if isinstance(body.get("pr_url"), str) else None
    repo_id_raw = body.get("repo_id")
    repo_id_uuid: UUID | None = None
    if isinstance(repo_id_raw, str) and repo_id_raw:
        try:
            repo_id_uuid = UUID(repo_id_raw)
        except ValueError:
            await _publish(
                {
                    "kind": "complete",
                    "state": "failed",
                    "error_category": "invalid_input",
                    "error_message": "Field 'repo_id' is not a valid UUID.",
                    "result": None,
                }
            )
            return {
                "error": {
                    "category": "invalid_input",
                    "message": "Field 'repo_id' is not a valid UUID.",
                    "retryable": False,
                }
            }

    service = ReviewService()
    try:
        await _publish(
            {
                "kind": "progress",
                "stage": "queued",
                "message": "Job picked up by worker.",
            }
        )
        if diff_in is not None:
            result = await service.run_for_diff(
                diff_in, repo_id=repo_id_uuid, on_stage=_on_stage
            )
        elif pr_url is not None:
            result = await service.run_for_url(
                pr_url, repo_id=repo_id_uuid, on_stage=_on_stage
            )
        else:
            err = "Either 'diff' or 'pr_url' is required."
            await _publish(
                {
                    "kind": "complete",
                    "state": "failed",
                    "error_category": "invalid_input",
                    "error_message": err,
                    "result": None,
                }
            )
            return {
                "error": {
                    "category": "invalid_input",
                    "message": err,
                    "retryable": False,
                }
            }
    except ReviewError as exc:
        _logger.warning(
            "review_job.failed",
            category=exc.category.value,
            message=exc.message,
            retryable=exc.retryable,
        )
        await _publish(
            {
                "kind": "complete",
                "state": "failed",
                "error_category": exc.category.value,
                "error_message": exc.message,
                "result": None,
            }
        )
        return {
            "error": {
                "category": exc.category.value,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        }
    except Exception as exc:  # noqa: BLE001 — defensive: unexpected provider/network surprises
        _logger.exception("review_job.unexpected_failure", error=str(exc))
        await _publish(
            {
                "kind": "complete",
                "state": "failed",
                "error_category": ReviewErrorCategory.INTERNAL.value,
                "error_message": "Unexpected server error.",
                "result": None,
            }
        )
        return {
            "error": {
                "category": ReviewErrorCategory.INTERNAL.value,
                "message": "Unexpected server error.",
                "retryable": True,
            }
        }

    result_payload = {
        "run_id": result.run_id,
        "verdict": str(result.verdict),
        "finding_count": len(result.findings),
        "provider": result.provider,
        "elapsed_ms": result.elapsed_ms,
    }
    await _publish(
        {
            "kind": "complete",
            "state": "success",
            "error_category": None,
            "error_message": None,
            "result": result_payload,
        }
    )
    return {"result": result_payload}
