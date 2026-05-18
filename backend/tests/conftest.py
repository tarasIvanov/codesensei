"""Shared pytest fixtures for backend tests."""

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient

from codesensei.main import create_app
from codesensei.providers.base import ProviderProbeResult, ProviderState


@pytest.fixture
def app():
    return create_app()


@pytest_asyncio.fixture
async def async_client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def _respx_block_unintercepted_http() -> Any:
    """Autouse — every outbound httpx call must be intercepted by respx.

    Tests that legitimately call the in-process ASGI transport are unaffected
    (ASGITransport does not go through respx). Any test that accidentally
    issues a real outbound httpx request will fail loudly.
    """
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock_router:
        yield mock_router


@pytest.fixture
def mock_probes(monkeypatch) -> Callable[..., None]:
    """Install fake probes in the healthcheck module.

    Usage:
        mock_probes({"db": "ok", "vector": "ok"}, "ok")
        mock_probes({"db": "ok", "vector": "ok"}, "ok",
                    llm=ProviderState.UNCONFIGURED)
    """

    def set_probes(
        db_result: dict[str, str],
        redis_status: str,
        *,
        llm: ProviderState = ProviderState.OK,
        embedding: ProviderState = ProviderState.OK,
    ) -> None:
        async def fake_probe_db():
            return dict(db_result)

        async def fake_probe_redis():
            return redis_status

        async def fake_probe_llm():
            return ProviderProbeResult(state=llm, provider="openai")

        async def fake_probe_embedding():
            return ProviderProbeResult(state=embedding, provider="openai")

        monkeypatch.setattr("codesensei.healthcheck.probe_db", fake_probe_db)
        monkeypatch.setattr("codesensei.healthcheck.probe_redis", fake_probe_redis)
        monkeypatch.setattr("codesensei.healthcheck.probe_llm_provider", fake_probe_llm)
        monkeypatch.setattr("codesensei.healthcheck.probe_embedding_provider", fake_probe_embedding)

    return set_probes
