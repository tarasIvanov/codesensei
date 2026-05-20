"""arq job — index a repository in the background (long-running)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from codesensei.indexing.errors import IndexError
from codesensei.indexing.service import IndexingService
from codesensei.jobs_stream import publisher as stream_publisher

_logger = structlog.get_logger()


async def index_repo_job(
    ctx: dict[str, Any],
    repo_id: str,
    source: str,  # noqa: ARG001 — kept for future signature parity / observability
    source_kind: str,  # noqa: ARG001
    default_branch: str | None,  # noqa: ARG001
) -> dict[str, Any]:
    """arq entry point. Returns the success or failure envelope per contract."""
    rid = UUID(repo_id)
    job_id = ctx.get("job_id")
    redis_client = ctx.get("redis")
    service = IndexingService.from_request()

    async def _on_progress(frame: dict[str, Any]) -> None:
        if job_id is None or redis_client is None:
            return
        try:
            await stream_publisher.publish(redis_client, str(job_id), frame)
        except Exception as exc:  # noqa: BLE001 — best-effort transport
            _logger.warning("stream_publish_failed", job_id=str(job_id), error=str(exc))

    try:
        if job_id is not None and redis_client is not None:
            await _on_progress(
                {
                    "kind": "progress",
                    "files_done": 0,
                    "files_total": None,
                    "chunks_done": 0,
                    "current_file": None,
                }
            )
        result = await service.run_for_existing_repo(rid, on_progress=_on_progress)
        if job_id is not None and redis_client is not None:
            await stream_publisher.publish(
                redis_client,
                str(job_id),
                {
                    "kind": "complete",
                    "state": "success",
                    "error_category": None,
                    "error_message": None,
                    "final_files": 0,
                    "final_chunks": int(result.get("chunk_count", 0) or 0),
                },
            )
        return result
    except IndexError as exc:
        _logger.warning(
            "index_repo_job.failed",
            repo_id=repo_id,
            category=exc.category.value,
            message=exc.message,
        )
        if job_id is not None and redis_client is not None:
            try:
                await stream_publisher.publish(
                    redis_client,
                    str(job_id),
                    {
                        "kind": "complete",
                        "state": "failed",
                        "error_category": exc.category.value,
                        "error_message": exc.message,
                        "final_files": 0,
                        "final_chunks": 0,
                    },
                )
            except Exception as pub_exc:  # noqa: BLE001
                _logger.warning(
                    "stream_publish_failed",
                    job_id=str(job_id),
                    error=str(pub_exc),
                )
        return {
            "repo_id": str(rid),
            "error": {
                "category": exc.category.value,
                "message": exc.message,
                "retryable": exc.retryable,
            },
        }
