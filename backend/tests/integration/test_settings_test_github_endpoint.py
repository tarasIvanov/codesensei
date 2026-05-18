"""Integration: GET /api/settings/test/github via the async ASGI client — feature 007."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

_URL = "https://api.github.com/user"
_ENDPOINT = "/api/settings/test/github"


@pytest.fixture(autouse=True)
def _mock_token(monkeypatch):
    monkeypatch.setattr(
        "codesensei.settings_store.api.store.get_setting",
        AsyncMock(return_value="fake-token"),
    )


@pytest.mark.asyncio
async def test_happy_path_returns_login_and_elapsed_ms(
    async_client, _respx_block_unintercepted_http
) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json={"login": "codesensei-bot"},
            headers={"X-GitHub-Token-Type": "fine-grained"},
        )
    )

    response = await async_client.get(_ENDPOINT)
    assert response.status_code == 200
    raw = response.text
    body = response.json()

    assert body["ok"] is True
    assert body["login"] == "codesensei-bot"
    assert body["scopes_hint"] == "fine-grained"
    assert isinstance(body["elapsed_ms"], int)
    # PAT MUST NOT appear anywhere in the response.
    assert "fake-token" not in raw


@pytest.mark.asyncio
async def test_no_token_returns_503_settings_locked(async_client, monkeypatch) -> None:
    monkeypatch.setattr(
        "codesensei.settings_store.api.store.get_setting",
        AsyncMock(return_value=None),
    )

    response = await async_client.get(_ENDPOINT)
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["category"] == "settings_locked"
    assert body["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_401_envelope_marks_github_auth_failed(
    async_client, _respx_block_unintercepted_http
) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(401, json={"message": "Bad credentials"})
    )

    response = await async_client.get(_ENDPOINT)
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["category"] == "github_auth_failed"
    assert body["error"]["retryable"] is False
    assert "fake-token" not in response.text


@pytest.mark.asyncio
async def test_429_envelope_carries_retry_after_seconds(
    async_client, _respx_block_unintercepted_http
) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "90"})
    )

    response = await async_client.get(_ENDPOINT)
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["category"] == "github_rate_limited"
    assert body["error"]["retryable"] is True
    assert body["retry_after_seconds"] == 90


@pytest.mark.asyncio
async def test_500_envelope_marks_retryable_true(
    async_client, _respx_block_unintercepted_http
) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(return_value=httpx.Response(500))

    response = await async_client.get(_ENDPOINT)
    assert response.status_code == 502
    body = response.json()
    assert body["error"]["category"] == "github_api_unavailable"
    assert body["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_pat_never_in_response(async_client, _respx_block_unintercepted_http) -> None:
    """Defence in depth: regardless of GitHub outcome, body must never carry the PAT."""
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(200, json={"login": "codesensei-bot"})
    )
    response = await async_client.get(_ENDPOINT)
    assert "fake-token" not in response.text
    assert "Authorization" not in response.text
