"""US1: POST /api/jobs/ping + GET /api/jobs/{id}."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from codesensei.tasks.errors import JobError, JobErrorCategory


@pytest.fixture
def _patch_enqueue(monkeypatch):
    def install(
        *,
        ping_result=None,
        ping_side_effect=None,
        lookup_result=None,
        lookup_side_effect=None,
    ):
        ping_mock = AsyncMock(
            return_value=ping_result if ping_side_effect is None else None,
            side_effect=ping_side_effect,
        )
        lookup_mock = AsyncMock(
            return_value=lookup_result if lookup_side_effect is None else None,
            side_effect=lookup_side_effect,
        )
        monkeypatch.setattr("codesensei.tasks.api.enqueue_ping", ping_mock)
        monkeypatch.setattr("codesensei.tasks.api.lookup_job", lookup_mock)
        return ping_mock, lookup_mock

    return install


async def test_post_ping_happy(async_client, _patch_enqueue):
    submitted = datetime(2026, 5, 17, 12, 34, 55, tzinfo=UTC)
    _patch_enqueue(ping_result=("0193abc", submitted))
    resp = await async_client.post("/api/jobs/ping", json={})
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == "0193abc"
    assert body["submitted_at"].startswith("2026-05-17T12:34:55")


async def test_post_ping_redis_down(async_client, _patch_enqueue):
    _patch_enqueue(
        ping_side_effect=JobError(
            JobErrorCategory.QUEUE_UNAVAILABLE, "Redis is not reachable.", retryable=True
        )
    )
    resp = await async_client.post("/api/jobs/ping", json={})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["category"] == "queue_unavailable"
    assert body["error"]["retryable"] is True


async def test_get_job_complete(async_client, _patch_enqueue):
    _patch_enqueue(
        lookup_result={
            "job_id": "0193abc",
            "status": "complete",
            "submitted_at": "2026-05-17T12:34:55+00:00",
            "completed_at": "2026-05-17T12:34:56+00:00",
            "result": {"stamped_at": "2026-05-17T12:34:56+00:00"},
        }
    )
    resp = await async_client.get("/api/jobs/0193abc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "complete"
    assert body["result"]["stamped_at"].startswith("2026-05-17T12:34:56")


async def test_get_job_pending(async_client, _patch_enqueue):
    _patch_enqueue(
        lookup_result={
            "job_id": "0193abc",
            "status": "pending",
            "submitted_at": "2026-05-17T12:34:55+00:00",
        }
    )
    resp = await async_client.get("/api/jobs/0193abc")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


async def test_get_job_not_found(async_client, _patch_enqueue):
    _patch_enqueue(
        lookup_side_effect=JobError(JobErrorCategory.NOT_FOUND, "job not found")
    )
    resp = await async_client.get("/api/jobs/unknown-id")
    assert resp.status_code == 404
    body = resp.json()
    assert body == {"job_id": "unknown-id", "status": "not_found"}


async def test_get_job_queue_unavailable(async_client, _patch_enqueue):
    _patch_enqueue(
        lookup_side_effect=JobError(
            JobErrorCategory.QUEUE_UNAVAILABLE, "Redis is not reachable.", retryable=True
        )
    )
    resp = await async_client.get("/api/jobs/0193abc")
    assert resp.status_code == 502
    assert resp.json()["error"]["category"] == "queue_unavailable"
