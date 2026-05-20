"""WebSocket endpoint `/api/jobs/{job_id}/stream` (feature 013)."""

from __future__ import annotations

import json
from datetime import UTC

import structlog
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from redis.exceptions import RedisError

from codesensei.config import get_settings
from codesensei.jobs_stream.publisher import channel_for

_logger = structlog.get_logger(__name__)

router = APIRouter(tags=["jobs"])

_JOB_NOT_FOUND_CODE = 4404


def _map_state(status: JobStatus) -> str:
    if status == JobStatus.queued or status == JobStatus.deferred:
        return "queued"
    if status == JobStatus.in_progress:
        return "running"
    if status == JobStatus.complete:
        return "success"
    return "queued"


@router.websocket("/jobs/{job_id}/stream")
async def jobs_stream(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    redis_url = get_settings().redis_url
    redis_client = Redis.from_url(redis_url, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = channel_for(job_id)
    try:
        await pubsub.subscribe(channel)
    except (RedisError, OSError) as exc:
        _logger.warning("jobs_stream_subscribe_failed", job_id=job_id, error=str(exc))
        await websocket.close(code=1011, reason="redis_unreachable")
        await redis_client.aclose()
        return

    arq_pool = None
    try:
        try:
            arq_pool = await create_pool(RedisSettings.from_dsn(redis_url))
            job = Job(job_id, redis=arq_pool)
            status = await job.status()
        except (RedisError, OSError) as exc:
            _logger.warning("jobs_stream_job_lookup_failed", job_id=job_id, error=str(exc))
            await websocket.close(code=1011, reason="arq_unreachable")
            return

        if status == JobStatus.not_found:
            await websocket.close(code=_JOB_NOT_FOUND_CODE, reason="job_not_found")
            return

        info = await job.info()
        started_iso = (
            info.enqueue_time.astimezone(UTC).isoformat() if info and info.enqueue_time else None
        )

        init_frame = {
            "kind": "init",
            "state": _map_state(status),
            "files_total": None,
            "files_done": 0,
            "chunks_done": 0,
            "started_at": started_iso,
            "eta_seconds": None,
        }
        await websocket.send_text(json.dumps(init_frame))

        if status == JobStatus.complete:
            result_info = await job.result_info()
            payload = result_info.result if result_info is not None else None
            error = (payload or {}).get("error") if isinstance(payload, dict) else None
            complete_state = "failed" if error is not None else "success"
            complete_frame = {
                "kind": "complete",
                "state": complete_state,
                "error_category": error.get("category") if error else None,
                "error_message": error.get("message") if error else None,
                "final_files": 0,
                "final_chunks": (payload or {}).get("chunk_count", 0)
                if isinstance(payload, dict)
                else 0,
            }
            await websocket.send_text(json.dumps(complete_frame))
            await websocket.close(code=1000)
            return

        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            await websocket.send_text(data)
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("kind") == "complete":
                await websocket.close(code=1000)
                return
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:  # noqa: BLE001
            pass
        try:
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
        await redis_client.aclose()
        if arq_pool is not None:
            await arq_pool.aclose()
