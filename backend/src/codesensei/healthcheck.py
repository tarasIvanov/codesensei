"""/healthz endpoint + envelope builder (003+004 contracts)."""

import asyncio
import time
from typing import Any, Literal

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from codesensei.db import probe_db
from codesensei.providers.base import ProviderProbeResult, ProviderState
from codesensei.providers.probe import probe_embedding_provider, probe_llm_provider
from codesensei.redis_client import probe_redis

router = APIRouter()

WorkerState = Literal["ok", "down", "unreachable"]


def build_envelope(
    db_result: dict[str, str],
    redis_status: str,
    llm_state: ProviderState,
    embedding_state: ProviderState,
    worker_state: WorkerState = "unreachable",
) -> tuple[int, dict[str, Any]]:
    """Pure: assemble the response envelope per contracts/healthz_v2.md + healthz_worker.md.

    Provider and worker states do NOT alter the overall `status` field (FR-013/FR-005)
    and do NOT contribute to `failing[]`.
    """
    failing: list[str] = []
    if db_result["db"] != "ok":
        failing.append("db")
    if redis_status != "ok":
        failing.append("redis")
    if db_result["vector"] != "ok":
        failing.append("vector")

    providers = {
        "llm": llm_state.value,
        "embedding": embedding_state.value,
    }

    if not failing:
        return 200, {
            "status": "ok",
            "db": "ok",
            "redis": "ok",
            "extensions": {"vector": "ok"},
            "providers": providers,
            "worker": worker_state,
        }
    return 503, {
        "status": "degraded",
        "db": db_result["db"],
        "redis": redis_status,
        "extensions": {"vector": db_result["vector"]},
        "providers": providers,
        "worker": worker_state,
        "failing": failing,
    }


async def probe_worker() -> WorkerState:
    """Read arq's heartbeat key from Redis; classify as ok/down/unreachable."""
    from codesensei.config import get_settings
    from codesensei.tasks.worker import HEALTH_CHECK_KEY

    settings = get_settings()
    logger = structlog.get_logger()
    try:
        import redis.asyncio as redis_asyncio
        from redis.exceptions import RedisError

        client = redis_asyncio.from_url(settings.redis_url, socket_timeout=1.0)
        try:
            raw = await asyncio.wait_for(client.get(HEALTH_CHECK_KEY), timeout=1.0)
        finally:
            await client.aclose()
    except (TimeoutError, OSError, RedisError) as exc:
        logger.warning("probe_worker.unreachable", error=str(exc))
        return "unreachable"
    except Exception as exc:  # noqa: BLE001
        logger.warning("probe_worker.unreachable", error=str(exc))
        return "unreachable"

    if raw is None:
        return "down"
    # arq stores a recent ISO-like string; freshness check is sufficient via key TTL,
    # but be defensive: just having the key present is enough for "ok".
    return "ok"


@router.get("/healthz")
async def healthz_handler() -> JSONResponse:
    logger = structlog.get_logger()
    started = time.perf_counter()
    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                probe_db(),
                probe_redis(),
                probe_llm_provider(),
                probe_embedding_provider(),
                probe_worker(),
            ),
            timeout=3.0,
        )
        db_result, redis_status, llm_probe, embedding_probe, worker_state = results
    except TimeoutError:
        db_result = {"db": "down", "vector": "unknown"}
        redis_status = "down"
        llm_probe = ProviderProbeResult(state=ProviderState.UNREACHABLE, provider=None)
        embedding_probe = ProviderProbeResult(state=ProviderState.UNREACHABLE, provider=None)
        worker_state = "unreachable"

    status_code, body = build_envelope(
        db_result, redis_status, llm_probe.state, embedding_probe.state, worker_state
    )
    duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    logger.info(
        "healthz",
        status=body["status"],
        db=body["db"],
        redis=body["redis"],
        vector=body["extensions"]["vector"],
        llm=body["providers"]["llm"],
        embedding=body["providers"]["embedding"],
        worker=body["worker"],
        duration_ms=duration_ms,
    )
    return JSONResponse(status_code=status_code, content=body)
