"""httpx client for the GitHub Reviews API POST call.

One outbound call per invocation. Status-code translation lives here so the
service layer only deals with already-typed `ReviewError` exceptions plus the
internal `_GitHub422` signal used to drive the body-only fallback.
"""

from __future__ import annotations

import httpx

from codesensei.review.errors import ReviewError, ReviewErrorCategory

_AUTH_MESSAGE = "PAT invalid or missing permissions (need pull_requests:write)."
_TIMEOUT_SECONDS = 15.0


class GitHub422(Exception):
    """Raised by post_review on a 422 response. Carries GitHub's JSON body so
    the service can decide whether to fall back to a body-only retry."""

    def __init__(self, body: dict[str, object], raw: str) -> None:
        super().__init__(raw)
        self.body = body
        self.raw = raw


def _api_unavailable(message: str) -> ReviewError:
    return ReviewError(ReviewErrorCategory.GITHUB_API_UNAVAILABLE, message, retryable=True)


def _parse_retry_after(response: httpx.Response) -> int:
    raw = response.headers.get("Retry-After", "")
    try:
        value = int(raw.strip())
    except (ValueError, AttributeError):
        return 60
    return value if value > 0 else 60


async def post_review(
    *,
    owner: str,
    repo: str,
    number: int,
    token: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """POST one review to GitHub. Returns parsed JSON on 200; raises otherwise."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/reviews"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "codesensei/0.0",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise _api_unavailable("GitHub request timed out.") from exc
    except httpx.ConnectError as exc:
        raise _api_unavailable("Could not reach GitHub.") from exc
    except httpx.HTTPError as exc:
        raise _api_unavailable(f"GitHub HTTP error: {exc}") from exc

    code = response.status_code
    if code == 200:
        return response.json()
    if code == 201:
        # GitHub historically returned 201 here too; be tolerant.
        return response.json()
    if code in (401, 403):
        raise ReviewError(ReviewErrorCategory.GITHUB_AUTH_FAILED, _AUTH_MESSAGE, retryable=False)
    if code == 404:
        raise ReviewError(
            ReviewErrorCategory.GITHUB_PR_NOT_FOUND,
            "GitHub could not find this PR. Check the URL and the bot's repo access.",
            retryable=False,
        )
    if code == 422:
        try:
            body = response.json()
        except ValueError:
            body = {}
        raise GitHub422(body=body, raw=response.text)
    if code == 429:
        retry_after = _parse_retry_after(response)
        raise ReviewError(
            ReviewErrorCategory.GITHUB_RATE_LIMITED,
            "GitHub rate limit hit.",
            retryable=True,
            retry_after_seconds=retry_after,
        )
    if 500 <= code < 600:
        raise _api_unavailable(f"GitHub returned HTTP {code}.")
    raise _api_unavailable(f"Unexpected GitHub status {code}: {response.text[:200]}")
