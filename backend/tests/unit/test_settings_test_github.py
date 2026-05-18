"""Unit tests for ``settings_store.github_probe.probe_github`` — feature 007."""

from __future__ import annotations

import httpx
import pytest

from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.settings_store.github_probe import probe_github

_URL = "https://api.github.com/user"


@pytest.mark.asyncio
async def test_happy_path_returns_login_and_scopes_hint(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json={"login": "codesensei-bot", "email": "private@example.com"},
            headers={"X-GitHub-Token-Type": "fine-grained"},
        )
    )

    result = await probe_github("fake-token")

    assert result == {"login": "codesensei-bot", "scopes_hint": "fine-grained"}
    assert "fake-token" not in str(result)


@pytest.mark.asyncio
async def test_happy_path_without_scopes_header(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(200, json={"login": "codesensei-bot"})
    )

    result = await probe_github("fake-token")

    assert result["login"] == "codesensei-bot"
    assert result["scopes_hint"] is None


@pytest.mark.asyncio
async def test_401_raises_github_auth_failed(_respx_block_unintercepted_http) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(401, json={"message": "Bad credentials"})
    )

    with pytest.raises(ReviewError) as exc:
        await probe_github("fake-token")

    assert exc.value.category == ReviewErrorCategory.GITHUB_AUTH_FAILED
    assert "401" in exc.value.message
    assert "fake-token" not in str(exc.value)


@pytest.mark.asyncio
async def test_403_raises_github_auth_failed(_respx_block_unintercepted_http) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )

    with pytest.raises(ReviewError) as exc:
        await probe_github("fake-token")

    assert exc.value.category == ReviewErrorCategory.GITHUB_AUTH_FAILED
    assert "403" in exc.value.message


@pytest.mark.asyncio
async def test_500_marks_retryable(_respx_block_unintercepted_http) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(ReviewError) as exc:
        await probe_github("fake-token")

    assert exc.value.category == ReviewErrorCategory.GITHUB_API_UNAVAILABLE
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_timeout_marks_retryable(_respx_block_unintercepted_http) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(side_effect=httpx.TimeoutException("boom"))

    with pytest.raises(ReviewError) as exc:
        await probe_github("fake-token")

    assert exc.value.category == ReviewErrorCategory.GITHUB_API_UNAVAILABLE
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_network_error_marks_retryable(_respx_block_unintercepted_http) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(side_effect=httpx.ConnectError("dns"))

    with pytest.raises(ReviewError) as exc:
        await probe_github("fake-token")

    assert exc.value.category == ReviewErrorCategory.GITHUB_API_UNAVAILABLE
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_429_surfaces_retry_after_seconds(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "75"})
    )

    with pytest.raises(ReviewError) as exc:
        await probe_github("fake-token")

    assert exc.value.category == ReviewErrorCategory.GITHUB_RATE_LIMITED
    assert exc.value.retryable is True
    assert exc.value.retry_after_seconds == 75


@pytest.mark.asyncio
async def test_429_without_retry_after_defaults_to_60(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.get(_URL).mock(return_value=httpx.Response(429))

    with pytest.raises(ReviewError) as exc:
        await probe_github("fake-token")

    assert exc.value.category == ReviewErrorCategory.GITHUB_RATE_LIMITED
    assert exc.value.retry_after_seconds == 60
