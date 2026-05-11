"""FastAPI app factory."""
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI

from codesensei.config import get_settings
from codesensei.healthcheck import router as healthcheck_router
from codesensei.logging_config import configure_logging


def _safe_host(url: str) -> str:
    """Return host portion of a URL without credentials."""
    parsed = urlparse(url)
    return parsed.hostname or "unknown"


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
    # /healthz (used by docker-compose healthcheck of api container)
    app.include_router(healthcheck_router)
    # /api/healthz (used by frontend via nginx proxy)
    app.include_router(healthcheck_router, prefix="/api")
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "codesensei.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
    )
