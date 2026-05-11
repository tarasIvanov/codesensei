"""Shared pytest fixtures for backend tests."""
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from codesensei.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest_asyncio.fixture
async def async_client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_probes(monkeypatch) -> Callable[[dict[str, str], str], None]:
    """Install fake probe_db / probe_redis in the healthcheck module.

    Usage:
        mock_probes({"db": "ok", "vector": "ok"}, "ok")
    """
    def set_probes(db_result: dict[str, str], redis_status: str) -> None:
        async def fake_probe_db():
            return dict(db_result)

        async def fake_probe_redis():
            return redis_status

        monkeypatch.setattr("codesensei.healthcheck.probe_db", fake_probe_db)
        monkeypatch.setattr("codesensei.healthcheck.probe_redis", fake_probe_redis)

    return set_probes
