"""POST /api/jobs/ping + GET /api/jobs/{job_id}."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from codesensei.tasks.enqueue import enqueue_ping, lookup_job
from codesensei.tasks.errors import JobError, JobErrorCategory

router = APIRouter(prefix="/jobs", tags=["jobs"])
_logger = structlog.get_logger()


@router.post("/ping")
async def post_ping() -> JSONResponse:
    try:
        job_id, submitted_at = await enqueue_ping()
    except JobError as exc:
        _logger.warning("jobs.failed", error_category=exc.category.value)
        raise
    except Exception:
        _logger.exception("jobs.failed", error_category="internal")
        raise JobError(JobErrorCategory.INTERNAL, "Unexpected server error.") from None
    _logger.info("jobs.ping.enqueued", job_id=job_id)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "submitted_at": submitted_at.isoformat()},
    )


@router.get("/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    try:
        body = await lookup_job(job_id)
    except JobError as exc:
        if exc.category == JobErrorCategory.NOT_FOUND:
            return JSONResponse(
                status_code=404,
                content={"job_id": job_id, "status": "not_found"},
            )
        _logger.warning("jobs.failed", error_category=exc.category.value, job_id=job_id)
        raise
    _logger.info("jobs.poll.read", job_id=job_id, status=body["status"])
    return JSONResponse(status_code=200, content=body)
