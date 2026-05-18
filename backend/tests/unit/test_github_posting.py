"""GitHub posting client + service: happy + failure paths via respx."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from codesensei.posting.schema import PostReviewRequest
from codesensei.posting.service import post_review_to_github
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.schema import Finding, ReviewResult, Severity, Verdict

_URL = "https://api.github.com/repos/owner/repo/pulls/42/reviews"


def _request(findings: list[Finding] | None = None, event: str = "COMMENT") -> PostReviewRequest:
    return PostReviewRequest(
        review_result=ReviewResult(
            verdict=Verdict.COMMENT,
            findings=findings
            or [Finding(file="a.py", line=1, severity=Severity.MAJOR, message="msg")],
            provider="openai",
            elapsed_ms=1234,
        ),
        pr_url="https://github.com/owner/repo/pull/42",
        event=event,
    )


@pytest.fixture(autouse=True)
def _mock_token(monkeypatch):
    monkeypatch.setattr(
        "codesensei.posting.service.get_setting",
        AsyncMock(return_value="fake-token"),
    )


@pytest.mark.asyncio
async def test_happy_path_returns_receipt(_respx_block_unintercepted_http) -> None:
    route = _respx_block_unintercepted_http.post(_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 999,
                "html_url": "https://github.com/owner/repo/pull/42#pullrequestreview-999",
            },
        )
    )
    receipt = await post_review_to_github(_request())
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["accept"] == "application/vnd.github+json"
    assert sent.headers["x-github-api-version"] == "2022-11-28"
    assert sent.headers["authorization"] == "Bearer fake-token"
    assert receipt.review_id == 999
    assert receipt.html_url.endswith("pullrequestreview-999")
    assert receipt.comment_count == 1
    assert receipt.attempted_calls == 1


@pytest.mark.asyncio
async def test_422_position_error_falls_back_to_body_only(
    _respx_block_unintercepted_http,
) -> None:
    route = _respx_block_unintercepted_http.post(_URL).mock(
        side_effect=[
            httpx.Response(
                422,
                json={
                    "message": "Validation Failed",
                    "errors": [{"resource": "PullRequestReviewComment", "field": "line"}],
                },
            ),
            httpx.Response(
                200,
                json={
                    "id": 1001,
                    "html_url": "https://github.com/owner/repo/pull/42#pullrequestreview-1001",
                },
            ),
        ]
    )
    receipt = await post_review_to_github(_request())
    assert route.call_count == 2
    assert receipt.review_id == 1001
    assert receipt.attempted_calls == 2
    assert receipt.comment_count == 0
    second_payload = route.calls[1].request.read()
    assert b'"comments": []' in second_payload or b'"comments":[]' in second_payload


@pytest.mark.asyncio
async def test_401_yields_github_auth_failed(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(return_value=httpx.Response(401, json={}))
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_AUTH_FAILED
    assert exc.value.retryable is False
    assert "pull_requests:write" in exc.value.message


@pytest.mark.asyncio
async def test_403_yields_github_auth_failed(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(return_value=httpx.Response(403, json={}))
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_AUTH_FAILED


@pytest.mark.asyncio
async def test_404_yields_pr_not_found(_respx_block_unintercepted_http) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(return_value=httpx.Response(404, json={}))
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_PR_NOT_FOUND
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_double_422_yields_review_rejected(
    _respx_block_unintercepted_http,
) -> None:
    body = {
        "message": "Validation Failed",
        "errors": [{"resource": "PullRequestReviewComment", "field": "line"}],
    }
    _respx_block_unintercepted_http.post(_URL).mock(return_value=httpx.Response(422, json=body))
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_REVIEW_REJECTED
    assert "Validation Failed" in exc.value.message


@pytest.mark.asyncio
async def test_structural_422_skips_fallback(
    _respx_block_unintercepted_http,
) -> None:
    body = {"message": "Invalid event value", "errors": []}
    route = _respx_block_unintercepted_http.post(_URL).mock(
        return_value=httpx.Response(422, json=body)
    )
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_REVIEW_REJECTED
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_500_yields_api_unavailable_retryable(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(return_value=httpx.Response(500, json={}))
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_API_UNAVAILABLE
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_504_yields_api_unavailable(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(return_value=httpx.Response(504, json={}))
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_API_UNAVAILABLE


@pytest.mark.asyncio
async def test_429_yields_rate_limited_with_retry_after(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(
        return_value=httpx.Response(429, json={}, headers={"Retry-After": "90"})
    )
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_RATE_LIMITED
    assert exc.value.retryable is True
    assert exc.value.retry_after_seconds == 90


@pytest.mark.asyncio
async def test_timeout_yields_api_unavailable(
    _respx_block_unintercepted_http,
) -> None:
    _respx_block_unintercepted_http.post(_URL).mock(side_effect=httpx.TimeoutException("slow"))
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.GITHUB_API_UNAVAILABLE
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_missing_token_yields_settings_locked(monkeypatch) -> None:
    monkeypatch.setattr(
        "codesensei.posting.service.get_setting",
        AsyncMock(return_value=None),
    )
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(_request())
    assert exc.value.category == ReviewErrorCategory.SETTINGS_LOCKED
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_invalid_pr_url_yields_invalid_input() -> None:
    bad = PostReviewRequest(
        review_result=ReviewResult(
            verdict=Verdict.APPROVE, findings=[], provider="openai", elapsed_ms=1
        ),
        pr_url="https://example.com/not-a-pr",
        event="COMMENT",
    )
    with pytest.raises(ReviewError) as exc:
        await post_review_to_github(bad)
    assert exc.value.category == ReviewErrorCategory.INVALID_INPUT
