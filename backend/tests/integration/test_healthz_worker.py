"""US1: /healthz envelope grows a `worker` field; state never gates overall."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("state", ["ok", "down", "unreachable"])
async def test_worker_state_reflected_and_never_gates_overall(
    async_client, monkeypatch, mock_probes, state
):
    mock_probes({"db": "ok", "vector": "ok"}, "ok")

    async def fake_worker():
        return state

    monkeypatch.setattr("codesensei.healthcheck.probe_worker", fake_worker)
    resp = await async_client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["worker"] == state
    assert "failing" not in body


async def test_worker_state_does_not_appear_in_failing(async_client, monkeypatch, mock_probes):
    mock_probes({"db": "down", "vector": "unknown"}, "ok")

    async def fake_worker():
        return "down"

    monkeypatch.setattr("codesensei.healthcheck.probe_worker", fake_worker)
    resp = await async_client.get("/healthz")
    assert resp.status_code == 503
    body = resp.json()
    assert "worker" not in body.get("failing", [])
    assert body["worker"] == "down"


async def test_api_healthz_alias_includes_worker(async_client, monkeypatch, mock_probes):
    mock_probes({"db": "ok", "vector": "ok"}, "ok")

    async def fake_worker():
        return "ok"

    monkeypatch.setattr("codesensei.healthcheck.probe_worker", fake_worker)
    resp = await async_client.get("/api/healthz")
    assert resp.status_code == 200
    assert resp.json()["worker"] == "ok"
