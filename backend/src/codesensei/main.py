"""FastAPI app factory."""
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from codesensei.config import get_settings
from codesensei.healthcheck import router as healthcheck_router
from codesensei.logging_config import configure_logging
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.router import router as review_router


def _safe_host(url: str) -> str:
    """Return host portion of a URL without credentials."""
    parsed = urlparse(url)
    return parsed.hostname or "unknown"


def _envelope_response(exc: ReviewError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())


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

    app = FastAPI(title="CodeSensei", version="0.0.0")

    @app.exception_handler(ReviewError)
    async def _review_error_handler(_request: Request, exc: ReviewError) -> JSONResponse:
        return _envelope_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Surface the first underlying ReviewError if pydantic wrapped one.
        for err in exc.errors():
            ctx = err.get("ctx") or {}
            inner = ctx.get("error")
            if isinstance(inner, ReviewError):
                return _envelope_response(inner)
        wrapped = ReviewError(
            ReviewErrorCategory.INVALID_INPUT,
            "Request body failed validation.",
        )
        return _envelope_response(wrapped)

    app.include_router(healthcheck_router)
    app.include_router(healthcheck_router, prefix="/api")
    app.include_router(review_router, prefix="/api")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "codesensei.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
    )
