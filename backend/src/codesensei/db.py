"""Async SQLAlchemy engine + session factory + DB probe for /healthz."""
import time
from typing import TypedDict

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from codesensei.config import get_settings


class DbProbeResult(TypedDict):
    db: str       # "ok" | "down"
    vector: str   # "ok" | "missing" | "unknown"


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def probe_db() -> DbProbeResult:
    logger = structlog.get_logger()
    started = time.perf_counter()
    sessionmaker = get_sessionmaker()
    try:
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
            ext_row = await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            vector_status = "ok" if ext_row.first() is not None else "missing"
        result: DbProbeResult = {"db": "ok", "vector": vector_status}
    except Exception as exc:
        logger.warning("probe.db.failure", error=str(exc))
        result = {"db": "down", "vector": "unknown"}
    duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    logger.info("probe.db", db=result["db"], vector=result["vector"], duration_ms=duration_ms)
    return result
