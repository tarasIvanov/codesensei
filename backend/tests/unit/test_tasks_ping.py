"""US1: ping_job pure-function test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from codesensei.tasks.ping import ping_job


async def test_ping_job_returns_iso_utc_timestamp():
    before = datetime.now(UTC)
    out = await ping_job({})
    after = datetime.now(UTC)
    assert isinstance(out, dict)
    assert "stamped_at" in out
    stamped = datetime.fromisoformat(out["stamped_at"])
    assert stamped.tzinfo is not None
    assert before - timedelta(seconds=2) <= stamped <= after + timedelta(seconds=2)


async def test_ping_job_ignores_ctx_contents():
    out_empty = await ping_job({})
    out_dirty = await ping_job({"junk": 1, "more": "stuff"})
    assert "stamped_at" in out_empty
    assert "stamped_at" in out_dirty
