"""Integration tests for /api/reviews + persist-on-review wiring — feature 009."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from codesensei.config import get_settings
from codesensei.reviews_history.models import ReviewFinding as DbFinding
from codesensei.reviews_history.models import ReviewRun as DbRun

_GOOD_DIFF = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_db_run(
    *,
    run_id: UUID | None = None,
    input_kind: str = "diff",
    pr_url: str | None = None,
    verdict: str = "comment",
    findings_data: list[dict] | None = None,
    has_temporal: bool = False,
) -> DbRun:
    run = DbRun(
        id=run_id or uuid4(),
        input_kind=input_kind,
        pr_url=pr_url,
        repo_id=None,
        diff=_GOOD_DIFF,
        verdict=verdict,
        provider="openai",
        elapsed_ms=42,
        finding_count=len(findings_data or []),
        has_temporal=has_temporal,
        context_files=None,
    )
    run.created_at = datetime.now(UTC)
    run.findings = []
    for i, f in enumerate(findings_data or []):
        df = DbFinding(
            run_id=run.id,
            position=i,
            file=f["file"],
            line=f.get("line"),
            severity=f["severity"],
            message=f["message"],
            suggestion=f.get("suggestion"),
            temporal_context=f.get("temporal_context"),
        )
        run.findings.append(df)
    return run


async def test_list_reviews_returns_summaries(async_client, monkeypatch):
    run = _make_db_run(verdict="approve")

    async def _fake_list(_session, *, limit):
        return [run]

    monkeypatch.setattr("codesensei.reviews_history.api.store.list_runs", _fake_list)

    resp = await async_client.get("/api/reviews")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "runs" in body
    assert len(body["runs"]) == 1
    row = body["runs"][0]
    assert row["id"] == str(run.id)
    assert row["verdict"] == "approve"
    assert row["provider"] == "openai"
    assert row["finding_count"] == 0
    assert row["has_temporal"] is False


async def test_list_reviews_clamps_limit(async_client, monkeypatch):
    captured = {}

    async def _fake_list(_session, *, limit):
        captured["limit"] = limit
        return []

    monkeypatch.setattr("codesensei.reviews_history.api.store.list_runs", _fake_list)

    # FastAPI Query validator rejects 250 (max=200) → 400.
    resp = await async_client.get("/api/reviews?limit=250")
    assert resp.status_code in (400, 422)


async def test_get_review_detail_returns_findings_with_temporal(async_client, monkeypatch):
    temporal = [
        {
            "commit_sha": "a" * 40,
            "short_sha": "aaaaaaa",
            "author_email": "alice@x.org",
            "author_date": "2026-01-15T10:42:13+00:00",
            "subject": "Fix race",
            "hunk_lines_changed": 7,
        }
    ]
    run = _make_db_run(
        verdict="request_changes",
        findings_data=[
            {
                "file": "x.py",
                "line": 1,
                "severity": "major",
                "message": "msg",
                "temporal_context": temporal,
            }
        ],
        has_temporal=True,
    )

    async def _fake_fetch(_session, _run_id):
        return run

    monkeypatch.setattr("codesensei.reviews_history.api.store.fetch_run", _fake_fetch)

    resp = await async_client.get(f"/api/reviews/{run.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(run.id)
    assert body["verdict"] == "request_changes"
    assert body["diff"] == _GOOD_DIFF
    assert len(body["findings"]) == 1
    f = body["findings"][0]
    assert f["file"] == "x.py"
    assert f["line"] == 1
    assert f["severity"] == "major"
    assert f["temporal_context"][0]["short_sha"] == "aaaaaaa"
    assert f["temporal_context"][0]["author_date"] == "2026-01-15T10:42:13+00:00"


async def test_get_review_detail_404_for_missing(async_client, monkeypatch):
    async def _fake_fetch(_session, _run_id):
        return None

    monkeypatch.setattr("codesensei.reviews_history.api.store.fetch_run", _fake_fetch)

    resp = await async_client.get(f"/api/reviews/{uuid4()}")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["category"] == "invalid_input"
    assert "not found" in body["error"]["message"].lower()


async def test_delete_review_204_then_404(async_client, monkeypatch):
    calls = {"count": 0}

    async def _fake_delete(_session, _run_id):
        calls["count"] += 1
        return calls["count"] == 1

    monkeypatch.setattr("codesensei.reviews_history.api.store.delete_run", _fake_delete)

    rid = uuid4()
    resp = await async_client.delete(f"/api/reviews/{rid}")
    assert resp.status_code == 204
    resp2 = await async_client.delete(f"/api/reviews/{rid}")
    assert resp2.status_code == 400
    assert resp2.json()["error"]["category"] == "invalid_input"


async def test_post_review_calls_persist(async_client, monkeypatch):
    """Successful POST /api/review invokes the persist module."""
    captured: dict = {}

    async def _fake_persist(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("codesensei.review.service._persist_run", _fake_persist)

    class _FakeProvider:
        name = "openai"

        async def chat(self, messages, **kw):
            return json.dumps(
                {
                    "verdict": "approve",
                    "findings": [],
                }
            )

    monkeypatch.setattr("codesensei.review.service.get_llm_provider", lambda: _FakeProvider())

    resp = await async_client.post("/api/review", json={"diff": _GOOD_DIFF})
    assert resp.status_code == 200, resp.text
    assert captured["input_kind"] == "diff"
    assert captured["pr_url"] is None
    assert captured["verdict"] == "approve"
    assert captured["provider_name"] == "openai"
    assert captured["diff"] == _GOOD_DIFF
    assert captured["findings"] == []


async def test_failed_review_does_not_persist(async_client, monkeypatch):
    """A provider error must NOT trigger persistence."""
    calls = {"count": 0}

    async def _fake_persist(**kwargs):
        calls["count"] += 1

    monkeypatch.setattr("codesensei.review.service._persist_run", _fake_persist)

    class _FakeProvider:
        name = "openai"

        async def chat(self, messages, **kw):
            from codesensei.providers.base import ProviderError

            raise ProviderError("openai", "boom", retryable=True)

    monkeypatch.setattr("codesensei.review.service.get_llm_provider", lambda: _FakeProvider())

    resp = await async_client.post("/api/review", json={"diff": _GOOD_DIFF})
    assert resp.status_code != 200
    assert calls["count"] == 0


async def test_persist_db_outage_does_not_break_live_response(async_client, monkeypatch):
    """A DB outage inside `_persist_run`'s try/except must NOT fail the live response."""

    def _raising_sessionmaker():
        raise RuntimeError("simulated db outage")

    monkeypatch.setattr("codesensei.review.service.get_sessionmaker", _raising_sessionmaker)

    class _FakeProvider:
        name = "openai"

        async def chat(self, messages, **kw):
            return json.dumps({"verdict": "approve", "findings": []})

    monkeypatch.setattr("codesensei.review.service.get_llm_provider", lambda: _FakeProvider())

    resp = await async_client.post("/api/review", json={"diff": _GOOD_DIFF})
    # Live response must still succeed (persist swallowed the DB error and logged a warning).
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "approve"
