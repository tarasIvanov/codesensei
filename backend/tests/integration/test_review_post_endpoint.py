"""Integration: POST /api/review/post via the async ASGI client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

_URL = "https://api.github.com/repos/owner/repo/pulls/42/reviews"


def _payload() -> dict:
    return {
        "review_result": {
            "verdict": "comment",
            "findings": [{"file": "a.py", "line": 3, "severity": "major", "message": "msg"}],
            "provider": "openai",
            "elapsed_ms": 1000,
        },
        "pr_url": "https://github.com/owner/repo/pull/42",
        "event": "COMMENT",
    }


@pytest.fixture(autouse=True)
def _mock_token(monkeypatch):
    monkeypatch.setattr(
        "codesensei.posting.service.get_setting",
        AsyncMock(return_value="fake-token"),
    )


@pytest.mark.asyncio
async def test_happy_path_returns_200_with_receipt(
    async_client, _respx_block_unintercepted_http
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(
        return_value=httpx.Response(
            200,
            json={"id": 7777, "html_url": "https://github.com/owner/repo/pull/42#x"},
        )
    )
    response = await async_client.post("/api/review/post", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["review_id"] == 7777
    assert body["comment_count"] == 1
    assert body["attempted_calls"] == 1
    assert body["html_url"].endswith("#x")


@pytest.mark.asyncio
async def test_invalid_pr_url_returns_400(async_client) -> None:
    bad = {**_payload(), "pr_url": "not a url"}
    response = await async_client.post("/api/review/post", json=bad)
    assert response.status_code == 400
    assert response.json()["error"]["category"] == "invalid_input"


@pytest.mark.asyncio
async def test_missing_token_returns_503(async_client, monkeypatch) -> None:
    monkeypatch.setattr(
        "codesensei.posting.service.get_setting",
        AsyncMock(return_value=None),
    )
    response = await async_client.post("/api/review/post", json=_payload())
    assert response.status_code == 503
    assert response.json()["error"]["category"] == "settings_locked"


@pytest.mark.asyncio
async def test_429_envelope_carries_retry_after_seconds(
    async_client, _respx_block_unintercepted_http
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(
        return_value=httpx.Response(429, json={}, headers={"Retry-After": "75"})
    )
    response = await async_client.post("/api/review/post", json=_payload())
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["category"] == "github_rate_limited"
    assert body["error"]["retryable"] is True
    assert body["retry_after_seconds"] == 75


@pytest.mark.asyncio
async def test_500_envelope_marks_retryable_true(
    async_client, _respx_block_unintercepted_http
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(return_value=httpx.Response(500, json={}))
    response = await async_client.post("/api/review/post", json=_payload())
    assert response.status_code == 502
    body = response.json()
    assert body["error"]["category"] == "github_api_unavailable"
    assert body["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_404_envelope_marks_retryable_false(
    async_client, _respx_block_unintercepted_http
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(return_value=httpx.Response(404, json={}))
    response = await async_client.post("/api/review/post", json=_payload())
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["category"] == "github_pr_not_found"
    assert body["error"]["retryable"] is False
