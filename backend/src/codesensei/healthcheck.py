"""/healthz endpoint + envelope builder (contracts/healthz.md, contracts/healthz_v2.md)."""
import asyncio
import time
from typing import Any

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from codesensei.db import probe_db
from codesensei.providers.base import ProviderProbeResult, ProviderState
from codesensei.providers.probe import probe_embedding_provider, probe_llm_provider
from codesensei.redis_client import probe_redis

router = APIRouter()


def build_envelope(
    db_result: dict[str, str],
    redis_status: str,
    llm_state: ProviderState,
    embedding_state: ProviderState,
) -> tuple[int, dict[str, Any]]:
    """Pure: assemble the response envelope per contracts/healthz_v2.md.

    Provider states do NOT alter the overall `status` field (FR-013) and do
    NOT contribute to `failing[]`.
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
        }
    return 503, {
        "status": "degraded",
        "db": db_result["db"],
        "redis": redis_status,
        "extensions": {"vector": db_result["vector"]},
        "providers": providers,
        "failing": failing,
    }


@router.get("/healthz")
async def healthz_handler() -> JSONResponse:
    logger = structlog.get_logger()
    started = time.perf_counter()
    try:
        db_result, redis_status, llm_probe, embedding_probe = await asyncio.wait_for(
            asyncio.gather(
                probe_db(),
                probe_redis(),
                probe_llm_provider(),
                probe_embedding_provider(),
            ),
            timeout=3.0,
        )
    except TimeoutError:
        db_result = {"db": "down", "vector": "unknown"}
        redis_status = "down"
        llm_probe = ProviderProbeResult(state=ProviderState.UNREACHABLE, provider=None)
        embedding_probe = ProviderProbeResult(state=ProviderState.UNREACHABLE, provider=None)

    status_code, body = build_envelope(
        db_result, redis_status, llm_probe.state, embedding_probe.state
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
        duration_ms=duration_ms,
    )
    return JSONResponse(status_code=status_code, content=body)
