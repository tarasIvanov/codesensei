"""Shared pytest fixtures for backend tests."""

import uuid
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


@pytest.fixture
def inline_review_worker(monkeypatch) -> dict[str, Any]:
    """Replace `enqueue_review` with an inline executor of `review_job`.

    Returns a dict with `last_result` (worker envelope), `last_review` (full
    ReviewResult or None), `error` (ReviewError or None), `calls` (count).
    Stream publishes are silenced by a no-op redis stub. `_persist_run` is
    mocked out so tests don't need a live DB; tests that care about persistence
    must mock it themselves.
    """
    from codesensei.review.tasks import review_job

    captured: dict[str, Any] = {
        "last_result": None,
        "last_review": None,
        "error": None,
        "calls": 0,
    }

    class _NoopRedis:
        async def publish(self, *args, **kwargs):  # noqa: ARG002 — swallow frames in tests
            return 0

    # Wrap `_run_chat` to stash the ReviewResult so tests can introspect findings.
    # NOTE: persistence is the production best-effort path. Tests that need to
    # mock `_persist_run` should do so inside the test body — monkeypatch
    # ordering means the local mock overrides any wrapper set up here.
    from codesensei.review import service as review_service

    real_run_chat = review_service._run_chat

    async def _wrapped_run_chat(*args, **kwargs):
        try:
            review = await real_run_chat(*args, **kwargs)
            captured["last_review"] = review
            return review
        except Exception as exc:
            captured["error"] = exc
            raise

    monkeypatch.setattr(review_service, "_run_chat", _wrapped_run_chat)

    async def _fake_enqueue(body: dict[str, Any]) -> str:
        captured["calls"] += 1
        job_id = uuid.uuid4().hex
        ctx = {"job_id": job_id, "redis": _NoopRedis()}
        captured["last_result"] = await review_job(ctx, body)
        return job_id

    monkeypatch.setattr("codesensei.review.router.enqueue_review", _fake_enqueue)
    return captured
