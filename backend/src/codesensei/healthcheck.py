"""/healthz endpoint + envelope builder (contracts/healthz.md)."""
import asyncio
import time
from typing import Any

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from codesensei.db import probe_db
from codesensei.redis_client import probe_redis

router = APIRouter()


def build_envelope(db_result: dict[str, str], redis_status: str) -> tuple[int, dict[str, Any]]:
    """Pure: assemble the response envelope per contracts/healthz.md.

    Inputs:
      db_result: {"db": "ok"|"down", "vector": "ok"|"missing"|"unknown"}
      redis_status: "ok"|"down"
    Output:
      (status_code, json_body)
    """
    failing: list[str] = []
    if db_result["db"] != "ok":
        failing.append("db")
    if redis_status != "ok":
        failing.append("redis")
    if db_result["vector"] != "ok":
        failing.append("vector")

    if not failing:
        return 200, {
            "status": "ok",
            "db": "ok",
            "redis": "ok",
            "extensions": {"vector": "ok"},
        }
    return 503, {
        "status": "degraded",
        "db": db_result["db"],
        "redis": redis_status,
        "extensions": {"vector": db_result["vector"]},
        "failing": failing,
    }


@router.get("/healthz")
async def healthz_handler() -> JSONResponse:
    logger = structlog.get_logger()
    started = time.perf_counter()
    try:
        db_result, redis_status = await asyncio.wait_for(
            asyncio.gather(probe_db(), probe_redis()),
            timeout=3.0,
        )
    except TimeoutError:
        db_result = {"db": "down", "vector": "unknown"}
        redis_status = "down"

    status_code, body = build_envelope(db_result, redis_status)
    duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    logger.info(
        "healthz",
        status=body["status"],
        db=body["db"],
        redis=body["redis"],
        vector=body["extensions"]["vector"],
        duration_ms=duration_ms,
    )
    return JSONResponse(status_code=status_code, content=body)
