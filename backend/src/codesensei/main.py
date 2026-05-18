"""FastAPI app factory."""

from contextlib import asynccontextmanager
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from codesensei.config import get_settings
from codesensei.healthcheck import router as healthcheck_router
from codesensei.indexing.api import router as indexing_router
from codesensei.indexing.errors import IndexError as _IdxError
from codesensei.logging_config import configure_logging
from codesensei.posting.api import router as posting_router
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.router import router as review_router
from codesensei.settings_store.api import router as settings_router
from codesensei.settings_store.runtime import (
    apply_store_overrides_to_env,
    snapshot_env_baseline,
)
from codesensei.tasks.api import router as jobs_router
from codesensei.tasks.errors import JobError


def _safe_host(url: str) -> str:
    """Return host portion of a URL without credentials."""
    parsed = urlparse(url)
    return parsed.hostname or "unknown"


def _review_envelope(exc: ReviewError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())


def _job_envelope(exc: JobError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())


def _index_envelope(exc: _IdxError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    snapshot_env_baseline()
    try:
        await apply_store_overrides_to_env()
    except Exception as exc:  # noqa: BLE001
        structlog.get_logger().warning("settings_store.startup_apply_failed", error=str(exc))
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    logger = structlog.get_logger()
    logger.info(
        "app.startup",
        llm_provider=settings.llm_provider,
        embedding_provider=settings.embedding_provider,
        database_host=_safe_host(settings.database_url),
        redis_host=_safe_host(settings.redis_url),
    )

    app = FastAPI(title="CodeSensei", version="0.0.0", lifespan=_lifespan)

    @app.exception_handler(ReviewError)
    async def _review_error_handler(_request: Request, exc: ReviewError) -> JSONResponse:
        return _review_envelope(exc)

    @app.exception_handler(JobError)
    async def _job_error_handler(_request: Request, exc: JobError) -> JSONResponse:
        return _job_envelope(exc)

    @app.exception_handler(_IdxError)
    async def _index_error_handler(_request: Request, exc: _IdxError) -> JSONResponse:
        return _index_envelope(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        for err in exc.errors():
            ctx = err.get("ctx") or {}
            inner = ctx.get("error")
            if isinstance(inner, ReviewError):
                return _review_envelope(inner)
        wrapped = ReviewError(
            ReviewErrorCategory.INVALID_INPUT,
            "Request body failed validation.",
        )
        return _review_envelope(wrapped)

    app.include_router(healthcheck_router)
    app.include_router(healthcheck_router, prefix="/api")
    app.include_router(review_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(indexing_router, prefix="/api")
    app.include_router(posting_router, prefix="/api")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "codesensei.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
    )
