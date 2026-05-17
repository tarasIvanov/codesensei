"""Thin async wrapper around arq for FastAPI handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from redis.exceptions import RedisError

from codesensei.config import get_settings
from codesensei.tasks.errors import JobError, JobErrorCategory

_logger = structlog.get_logger()


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def enqueue_ping() -> tuple[str, datetime]:
    """Enqueue ping_job; return (job_id, submitted_at)."""
    try:
        pool = await create_pool(_redis_settings())
    except (RedisError, OSError) as exc:
        raise JobError(
            JobErrorCategory.QUEUE_UNAVAILABLE,
            "Redis is not reachable.",
            retryable=True,
        ) from exc
    try:
        job = await pool.enqueue_job("ping_job")
        if job is None:
            raise JobError(
                JobErrorCategory.INTERNAL,
                "arq returned no job handle.",
            )
        submitted_at = datetime.now(UTC)
        return job.job_id, submitted_at
    finally:
        await pool.aclose()


async def enqueue_index_repo(
    *,
    repo_id: Any,
    source: str,
    source_kind: str,
    default_branch: str | None,
) -> str:
    """Enqueue index_repo_job; return job_id."""
    try:
        pool = await create_pool(_redis_settings())
    except (RedisError, OSError) as exc:
        raise JobError(
            JobErrorCategory.QUEUE_UNAVAILABLE,
            "Redis is not reachable.",
            retryable=True,
        ) from exc
    try:
        job = await pool.enqueue_job(
            "index_repo_job",
            str(repo_id),
            source,
            source_kind,
            default_branch,
        )
        if job is None:
            raise JobError(JobErrorCategory.INTERNAL, "arq returned no job handle.")
        return job.job_id
    finally:
        await pool.aclose()


async def lookup_job(job_id: str) -> dict[str, Any]:
    """Return the same wire shape as contracts/api_jobs.md GET success/not-found."""
    if not job_id or len(job_id) > 200:
        raise JobError(JobErrorCategory.INVALID_INPUT, "job_id is required.")
    try:
        pool = await create_pool(_redis_settings())
    except (RedisError, OSError) as exc:
        raise JobError(
            JobErrorCategory.QUEUE_UNAVAILABLE,
            "Redis is not reachable.",
            retryable=True,
        ) from exc
    try:
        job = Job(job_id, redis=pool)
        status = await job.status()
        if status == JobStatus.not_found:
            raise JobError(JobErrorCategory.NOT_FOUND, "job not found")
        info = await job.info()
        body: dict[str, Any] = {
            "job_id": job_id,
            "status": _map_status(status),
        }
        if info is not None and info.enqueue_time is not None:
            body["submitted_at"] = info.enqueue_time.astimezone(UTC).isoformat()
        if status == JobStatus.complete:
            result_info = await job.result_info()
            if result_info is not None:
                body["completed_at"] = result_info.finish_time.astimezone(UTC).isoformat()
                body["result"] = result_info.result
        return body
    finally:
        await pool.aclose()


def _map_status(status: JobStatus) -> str:
    if status == JobStatus.queued or status == JobStatus.deferred:
        return "pending"
    if status == JobStatus.in_progress:
        return "in_progress"
    if status == JobStatus.complete:
        return "complete"
    return "pending"
