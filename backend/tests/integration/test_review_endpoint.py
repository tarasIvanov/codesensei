"""Integration tests for POST /api/review."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from codesensei.config import get_settings

_GOOD_DIFF = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _FakeProvider:
    def __init__(self, name: str, chat_mock: AsyncMock):
        self.name = name
        self._mock = chat_mock

    async def chat(self, messages, **kwargs):
        return await self._mock(messages, **kwargs)


def _install_provider(monkeypatch, *, return_value=None, side_effect=None, name="openai"):
    mock = (
        AsyncMock(side_effect=side_effect) if side_effect else AsyncMock(return_value=return_value)
    )
    fake = _FakeProvider(name, mock)
    monkeypatch.setattr("codesensei.review.service.get_llm_provider", lambda: fake)
    return mock


def _envelope(findings, verdict="comment") -> str:
    return json.dumps({"verdict": verdict, "findings": findings})


async def test_post_review_happy_diff(async_client, monkeypatch):
    raw = _envelope(
        [{"file": "x.py", "line": 1, "severity": "major", "message": "ahem"}],
        verdict="request_changes",
    )
    _install_provider(monkeypatch, return_value=raw)
    resp = await async_client.post("/api/review", json={"diff": _GOOD_DIFF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "request_changes"
    assert body["provider"] == "openai"
    assert len(body["findings"]) == 1
    assert body["findings"][0]["severity"] == "major"
    assert isinstance(body["elapsed_ms"], int)


async def test_post_review_clean_diff(async_client, monkeypatch):
    _install_provider(monkeypatch, return_value=_envelope([], verdict="approve"))
    resp = await async_client.post("/api/review", json={"diff": _GOOD_DIFF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["findings"] == []
    assert body["verdict"] == "approve"


async def test_post_review_empty_body(async_client):
    resp = await async_client.post("/api/review", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["category"] == "invalid_input"


async def test_post_review_both_diff_and_url(async_client):
    resp = await async_client.post(
        "/api/review",
        json={"diff": _GOOD_DIFF, "pr_url": "https://github.com/o/r/pull/1"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["category"] == "invalid_input"


async def test_post_review_non_diff_text(async_client):
    resp = await async_client.post("/api/review", json={"diff": "not a diff at all"})
    assert resp.status_code == 400
    assert resp.json()["error"]["category"] == "invalid_input"


async def test_post_review_malformed_pr_url(async_client):
    resp = await async_client.post("/api/review", json={"pr_url": "https://gitlab.com/o/r/pull/1"})
    assert resp.status_code == 400
    assert resp.json()["error"]["category"] == "invalid_input"


async def test_post_review_malformed_llm_output(async_client, monkeypatch):
    _install_provider(monkeypatch, return_value="this is not JSON")
    resp = await async_client.post("/api/review", json={"diff": _GOOD_DIFF})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["category"] == "provider_malformed_output"
    assert body["error"]["retryable"] is False


async def test_post_review_provider_unavailable(async_client, monkeypatch):
    from codesensei.providers import ProviderError

    _install_provider(monkeypatch, side_effect=ProviderError("openai", "503 down", retryable=True))
    resp = await async_client.post("/api/review", json={"diff": _GOOD_DIFF})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["category"] == "provider_unavailable"
    assert body["error"]["retryable"] is True


async def test_post_review_payload_too_large(async_client, monkeypatch):
    import time

    monkeypatch.setenv("REVIEW_MAX_DIFF_BYTES", "1000")
    get_settings.cache_clear()
    mock = _install_provider(monkeypatch, return_value=_envelope([], verdict="approve"))
    big = _GOOD_DIFF + "+" + ("x" * 2000) + "\n"
    started = time.perf_counter()
    resp = await async_client.post("/api/review", json={"diff": big})
    elapsed = time.perf_counter() - started
    assert resp.status_code == 413
    assert resp.json()["error"]["category"] == "payload_too_large"
    assert mock.call_count == 0
    assert elapsed < 1.0, f"oversize rejection took {elapsed:.3f}s (>1s budget)"


async def test_post_review_logs_carry_error_category(async_client, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("REVIEW_MAX_DIFF_BYTES", "1000")
    get_settings.cache_clear()
    _install_provider(monkeypatch, return_value=_envelope([], verdict="approve"))
    big = _GOOD_DIFF + "+" + ("CANARY_DIFF_BODY_Z9" * 200) + "\n"
    await async_client.post("/api/review", json={"diff": big})
    blob = " ".join(rec.getMessage() for rec in caplog.records) + " ".join(
        str(rec.args or "") for rec in caplog.records
    )
    # body content never logged
    assert "CANARY_DIFF_BODY_Z9" not in blob


async def test_post_review_logs_no_diff_body(async_client, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO)
    _install_provider(monkeypatch, return_value=_envelope([], verdict="approve"))
    secret_diff = _GOOD_DIFF.replace("+new", "+SECRET_TOKEN_CANARY_X9")
    await async_client.post("/api/review", json={"diff": secret_diff})
    log_blob = " ".join(rec.message for rec in caplog.records) + " ".join(
        str(rec.args or "") for rec in caplog.records
    )
    assert "SECRET_TOKEN_CANARY_X9" not in log_blob


# === US2 — PR URL fetch path ===


_API = "https://api.github.com/repos/octo/repo/pulls/7"
_PR_URL = "https://github.com/octo/repo/pull/7"


async def test_post_review_pr_url_happy(async_client, monkeypatch, _respx_block_unintercepted_http):
    import httpx

    _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(200, text=_GOOD_DIFF)
    )
    _install_provider(
        monkeypatch,
        return_value=_envelope(
            [{"file": "x.py", "line": 1, "severity": "nit", "message": "ok"}],
            verdict="comment",
        ),
    )
    resp = await async_client.post("/api/review", json={"pr_url": _PR_URL})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "comment"
    assert body["findings"][0]["file"] == "x.py"


async def test_post_review_pr_url_404(async_client, monkeypatch, _respx_block_unintercepted_http):
    import httpx

    _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    _install_provider(monkeypatch, return_value=_envelope([], verdict="approve"))
    resp = await async_client.post("/api/review", json={"pr_url": _PR_URL})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["category"] == "github_fetch_failed"
    assert "not found" in body["error"]["message"].lower()


async def test_post_review_pr_url_malformed(async_client):
    resp = await async_client.post("/api/review", json={"pr_url": "https://gitlab.com/o/r/pull/1"})
    assert resp.status_code == 400
    assert resp.json()["error"]["category"] == "invalid_input"
