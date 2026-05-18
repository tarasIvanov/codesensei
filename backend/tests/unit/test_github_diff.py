"""US2: GitHub diff fetcher — happy path + error normalization, fully offline."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from codesensei.config import get_settings
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.github_diff import fetch_pr_diff

_API = "https://api.github.com/repos/octo/repo/pulls/7"
_PR_URL = "https://github.com/octo/repo/pull/7"
_DIFF_BODY = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_fetch_happy(_respx_block_unintercepted_http: respx.MockRouter):
    _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(200, text=_DIFF_BODY)
    )
    out = await fetch_pr_diff(_PR_URL)
    assert out == _DIFF_BODY


async def test_fetch_sends_auth_when_token(
    monkeypatch, _respx_block_unintercepted_http: respx.MockRouter
):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_abc123")
    get_settings.cache_clear()
    route = _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(200, text=_DIFF_BODY)
    )
    await fetch_pr_diff(_PR_URL)
    sent_headers = route.calls.last.request.headers
    assert sent_headers["Authorization"] == "Bearer ghp_abc123"
    assert sent_headers["Accept"] == "application/vnd.github.v3.diff"


async def test_fetch_omits_auth_when_no_token(
    _respx_block_unintercepted_http: respx.MockRouter,
):
    route = _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(200, text=_DIFF_BODY)
    )
    await fetch_pr_diff(_PR_URL)
    sent_headers = route.calls.last.request.headers
    assert "Authorization" not in sent_headers


async def test_fetch_401(_respx_block_unintercepted_http: respx.MockRouter):
    _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(401, json={"message": "Bad credentials"})
    )
    with pytest.raises(ReviewError) as exc:
        await fetch_pr_diff(_PR_URL)
    assert exc.value.category is ReviewErrorCategory.GITHUB_FETCH_FAILED
    assert "auth" in exc.value.message.lower()


async def test_fetch_403(_respx_block_unintercepted_http: respx.MockRouter):
    _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(403, json={"message": "Forbidden"})
    )
    with pytest.raises(ReviewError) as exc:
        await fetch_pr_diff(_PR_URL)
    assert exc.value.category is ReviewErrorCategory.GITHUB_FETCH_FAILED


async def test_fetch_404(_respx_block_unintercepted_http: respx.MockRouter):
    _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    with pytest.raises(ReviewError) as exc:
        await fetch_pr_diff(_PR_URL)
    assert exc.value.category is ReviewErrorCategory.GITHUB_FETCH_FAILED
    assert "not found" in exc.value.message.lower()


async def test_fetch_500(_respx_block_unintercepted_http: respx.MockRouter):
    _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(500, json={"message": "boom"})
    )
    with pytest.raises(ReviewError) as exc:
        await fetch_pr_diff(_PR_URL)
    assert exc.value.category is ReviewErrorCategory.GITHUB_FETCH_FAILED


async def test_fetch_timeout(_respx_block_unintercepted_http: respx.MockRouter):
    _respx_block_unintercepted_http.get(_API).mock(side_effect=httpx.TimeoutException("slow"))
    with pytest.raises(ReviewError) as exc:
        await fetch_pr_diff(_PR_URL)
    assert exc.value.category is ReviewErrorCategory.GITHUB_FETCH_FAILED
    assert "timed out" in exc.value.message.lower()


async def test_fetch_connect_error(_respx_block_unintercepted_http: respx.MockRouter):
    _respx_block_unintercepted_http.get(_API).mock(side_effect=httpx.ConnectError("dns"))
    with pytest.raises(ReviewError) as exc:
        await fetch_pr_diff(_PR_URL)
    assert exc.value.category is ReviewErrorCategory.GITHUB_FETCH_FAILED


async def test_fetch_invalid_url_raises_invalid_input():
    with pytest.raises(ReviewError) as exc:
        await fetch_pr_diff("https://gitlab.com/o/r/pull/1")
    assert exc.value.category is ReviewErrorCategory.INVALID_INPUT


async def test_fetch_never_logs_token(
    monkeypatch, caplog, _respx_block_unintercepted_http: respx.MockRouter
):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_TOKEN_CANARY_X9")
    get_settings.cache_clear()
    caplog.set_level(logging.DEBUG)
    _respx_block_unintercepted_http.get(_API).mock(
        return_value=httpx.Response(401, json={"message": "no"})
    )
    with pytest.raises(ReviewError):
        await fetch_pr_diff(_PR_URL)
    blob = " ".join(rec.getMessage() for rec in caplog.records) + " ".join(
        str(rec.args or "") for rec in caplog.records
    )
    assert "ghp_TOKEN_CANARY_X9" not in blob
