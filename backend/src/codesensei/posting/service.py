"""Orchestrator for POST /api/review/post.

Flow: parse pr_url → read PAT → build payload → POST to GitHub →
optionally retry body-only on 422-position errors → return receipt.
Emits one `github_review_posted` structlog line per attempt.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

import structlog

from codesensei.posting import client as github_client
from codesensei.posting.mapper import build_payload
from codesensei.posting.schema import PostedReviewReceipt, PostReviewRequest
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.settings_store.store import get_setting

_logger = structlog.get_logger()

_PR_URL_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)$")
_POSITION_FIELDS = {"path", "line", "position", "start_line"}
_POSITION_MESSAGE_HINT = "not part of the pull request diff"


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    match = _PR_URL_RE.match(pr_url or "")
    if not match:
        raise ReviewError(
            ReviewErrorCategory.INVALID_INPUT,
            "PR URL must match https://github.com/<owner>/<repo>/pull/<n>.",
        )
    owner, repo, number = match.groups()
    return owner, repo, int(number)


def _is_position_error(body: dict[str, object]) -> bool:
    errors = body.get("errors")
    if isinstance(errors, list):
        for entry in errors:
            if not isinstance(entry, dict):
                continue
            resource = entry.get("resource")
            field = entry.get("field")
            if (
                resource == "PullRequestReviewComment"
                and isinstance(field, str)
                and field in _POSITION_FIELDS
            ):
                return True
    message = body.get("message")
    if isinstance(message, str) and _POSITION_MESSAGE_HINT in message.lower():
        return True
    return False


async def post_review_to_github(req: PostReviewRequest) -> PostedReviewReceipt:
    started = time.perf_counter()
    outcome = "ok"
    review_id: int | None = None
    comment_count = 0
    body_chars = 0
    attempted_calls = 0
    owner: str | None = None
    repo: str | None = None
    number: int | None = None
    try:
        owner, repo, number = parse_pr_url(req.pr_url)
        token = await get_setting("GITHUB_TOKEN")
        if not token:
            raise ReviewError(
                ReviewErrorCategory.SETTINGS_LOCKED,
                "No GitHub bot token configured. Open Settings to add one.",
                retryable=False,
            )
        payload = build_payload(req.review_result, req.event)
        comment_count = len(payload.get("comments") or [])
        body_chars = len(str(payload.get("body") or ""))
        attempted_calls = 1
        try:
            gh_response = await github_client.post_review(
                owner=owner,
                repo=repo,
                number=number,
                token=token,
                payload=payload,
            )
        except github_client.GitHub422 as first_422:
            if not _is_position_error(first_422.body):
                raise ReviewError(
                    ReviewErrorCategory.GITHUB_REVIEW_REJECTED,
                    f"GitHub refused the review: {first_422.raw[:1000]}",
                    retryable=False,
                ) from first_422
            attempted_calls = 2
            fallback_payload = {**payload, "comments": []}
            comment_count = 0
            body_chars = len(str(fallback_payload.get("body") or ""))
            try:
                gh_response = await github_client.post_review(
                    owner=owner,
                    repo=repo,
                    number=number,
                    token=token,
                    payload=fallback_payload,
                )
            except github_client.GitHub422 as second_422:
                raise ReviewError(
                    ReviewErrorCategory.GITHUB_REVIEW_REJECTED,
                    f"GitHub refused the body-only fallback: {second_422.raw[:1000]}",
                    retryable=False,
                ) from second_422
        review_id_raw = gh_response.get("id")
        if not isinstance(review_id_raw, int):
            raise ReviewError(
                ReviewErrorCategory.GITHUB_REVIEW_REJECTED,
                "GitHub response missing numeric 'id'.",
                retryable=False,
            )
        review_id = review_id_raw
        html_url_raw = gh_response.get("html_url")
        if not isinstance(html_url_raw, str):
            raise ReviewError(
                ReviewErrorCategory.GITHUB_REVIEW_REJECTED,
                "GitHub response missing 'html_url'.",
                retryable=False,
            )
        return PostedReviewReceipt(
            review_id=review_id,
            html_url=html_url_raw,
            posted_at=datetime.now(UTC),
            comment_count=comment_count,
            attempted_calls=attempted_calls,
        )
    except ReviewError as exc:
        outcome = exc.category.value
        raise
    except Exception:
        outcome = ReviewErrorCategory.INTERNAL.value
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _logger.info(
            "github_review_posted",
            pr_url=req.pr_url,
            gh_event=req.event,
            comment_count=comment_count,
            body_chars=body_chars,
            elapsed_ms=elapsed_ms,
            review_id=review_id,
            outcome=outcome,
            attempted_calls=attempted_calls,
        )
