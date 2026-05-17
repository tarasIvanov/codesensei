"""Async Redis client + Redis probe for /healthz."""

import time

import redis.asyncio as aioredis
import structlog

from codesensei.config import get_settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def probe_redis() -> str:
    logger = structlog.get_logger()
    started = time.perf_counter()
    client = get_redis()
    try:
        pong = await client.ping()
        status = "ok" if pong else "down"
    except Exception as exc:
        logger.warning("probe.redis.failure", error=str(exc))
        status = "down"
    duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    logger.info("probe.redis", redis=status, duration_ms=duration_ms)
    return status
