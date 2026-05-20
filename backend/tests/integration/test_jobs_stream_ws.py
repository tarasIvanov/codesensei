"""Integration tests for `WS /api/jobs/{job_id}/stream` (feature 013).

The full progress→complete roundtrip is verified manually via quickstart.md;
the unit tests in test_jobs_stream_publisher.py already cover the pub/sub
shape, and FastAPI's TestClient runs WS in a separate thread which makes
cross-loop fakeredis publishing flaky in CI. Here we verify the
unknown-job 4404 handshake — a tight contract guarantee from the close-code
table.
"""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from starlette.testclient import TestClient


@pytest.fixture
def app_unknown_job(monkeypatch):
    from codesensei import main as app_main
    from codesensei.jobs_stream import router as ws_router

    shared = FakeRedis()

    def _fake_from_url(*args, **kwargs):  # noqa: ARG001
        return shared

    async def _fake_create_pool(*args, **kwargs):  # noqa: ARG001
        return shared

    class _FakeJob:
        def __init__(self, job_id, redis=None):  # noqa: ARG002
            self._id = job_id

        async def status(self):
            from arq.jobs import JobStatus

            return JobStatus.not_found

        async def info(self):
            return None

        async def result_info(self):
            return None

    monkeypatch.setattr(
        ws_router,
        "Redis",
        type("_R", (), {"from_url": staticmethod(_fake_from_url)}),
    )
    monkeypatch.setattr(ws_router, "create_pool", _fake_create_pool)
    monkeypatch.setattr(ws_router, "Job", _FakeJob)
    return app_main.create_app()


def test_unknown_job_id_closes_with_4404(app_unknown_job):
    from starlette.websockets import WebSocketDisconnect

    client = TestClient(app_unknown_job)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/jobs/missing-job/stream") as ws:
            # The server accepts then closes; receive_* surfaces the close.
            ws.receive_text()
    assert exc_info.value.code == 4404
