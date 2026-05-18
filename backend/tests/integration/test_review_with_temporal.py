"""Integration: /api/review wires temporal context onto findings — feature 008."""

from __future__ import annotations

import json

import pytest

from codesensei.config import get_settings
from codesensei.review.git_temporal import (
    LineWindow,
    TemporalCollectionSummary,
    TemporalEntry,
)

_DIFF = "\n".join(
    [
        "diff --git a/src/x.py b/src/x.py",
        "--- a/src/x.py",
        "+++ b/src/x.py",
        "@@ -40,3 +40,3 @@",
        "-old1",
        "-old2",
        "-old3",
        "+new1",
        "+new2",
        "+new3",
        "",
    ]
)


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _FakeProvider:
    def __init__(self, name: str, raw: str) -> None:
        self.name = name
        self._raw = raw

    async def chat(self, messages, **kwargs) -> str:
        return self._raw


def _entry(short: str, subject: str) -> TemporalEntry:
    return TemporalEntry(
        commit_sha=short + "0" * (40 - len(short)),
        short_sha=short[:7].ljust(7, "0"),
        author_email="dev@example.org",
        author_date="2026-01-15T10:42:13+00:00",
        subject=subject,
        hunk_lines_changed=2,
    )


async def test_review_attaches_temporal_to_matching_finding(async_client, monkeypatch):
    pool = {
        "src/x.py": [
            (
                LineWindow(40, 60),
                [_entry("abc1234", "Fix bug"), _entry("def5678", "Add test")],
            )
        ]
    }
    summary = TemporalCollectionSummary(repo_id=None, files_count=1, entries_total=2, elapsed_ms=42)

    async def _fake_pool(**_kwargs):
        return pool, summary

    monkeypatch.setattr("codesensei.review.service.fetch_temporal_pool_for_review", _fake_pool)

    async def _fake_resolve(_repo_id):
        return "https://example.org/repo"

    monkeypatch.setattr("codesensei.review.service._resolve_repo_source", _fake_resolve)

    # RAG retrieval — short-circuit to empty.
    class _R:
        selected = []

    async def _fake_retrieve(_repo_id, _diff):
        return _R()

    monkeypatch.setattr("codesensei.review.service._retrieve_context", _fake_retrieve)

    raw = json.dumps(
        {
            "verdict": "request_changes",
            "findings": [
                {
                    "file": "src/x.py",
                    "line": 45,
                    "severity": "major",
                    "message": "matched",
                },
                {
                    "file": "src/y.py",
                    "line": 12,
                    "severity": "minor",
                    "message": "unmatched",
                },
            ],
        }
    )
    monkeypatch.setattr(
        "codesensei.review.service.get_llm_provider",
        lambda: _FakeProvider("openai", raw),
    )

    resp = await async_client.post(
        "/api/review",
        json={"diff": _DIFF, "repo_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    findings = body["findings"]
    assert len(findings) == 2

    matched = next(f for f in findings if f["file"] == "src/x.py")
    assert matched["temporal_context"] is not None
    assert len(matched["temporal_context"]) == 2
    assert matched["temporal_context"][0]["short_sha"].startswith("abc1234")
    assert matched["temporal_context"][0]["author_date"] == "2026-01-15T10:42:13+00:00"

    unmatched = next(f for f in findings if f["file"] == "src/y.py")
    assert unmatched.get("temporal_context") in (None, [])


async def test_review_without_repo_id_skips_temporal(async_client, monkeypatch):
    calls = {"count": 0}

    async def _fake_pool(**_kwargs):
        calls["count"] += 1
        return {}, TemporalCollectionSummary()

    monkeypatch.setattr("codesensei.review.service.fetch_temporal_pool_for_review", _fake_pool)
    raw = json.dumps({"verdict": "approve", "findings": []})
    monkeypatch.setattr(
        "codesensei.review.service.get_llm_provider",
        lambda: _FakeProvider("openai", raw),
    )

    resp = await async_client.post("/api/review", json={"diff": _DIFF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "approve"
    assert calls["count"] == 0
    # No temporal_context anywhere — but findings list is empty so just confirm key absent.
    for f in body["findings"]:
        assert "temporal_context" not in f or f["temporal_context"] is None
