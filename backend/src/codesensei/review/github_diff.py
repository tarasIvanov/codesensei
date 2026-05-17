"""GitHub PR diff fetcher — REST + Accept: application/vnd.github.v3.diff."""

from __future__ import annotations

import re

import httpx

from codesensei.config import get_settings
from codesensei.review.errors import ReviewError, ReviewErrorCategory

_PR_URL_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)$")
_TIMEOUT_SECONDS = 10.0


def _fail(message: str) -> ReviewError:
    return ReviewError(ReviewErrorCategory.GITHUB_FETCH_FAILED, message, retryable=False)


async def fetch_pr_diff(pr_url: str) -> str:
    match = _PR_URL_RE.match(pr_url)
    if not match:
        raise ReviewError(
            ReviewErrorCategory.INVALID_INPUT,
            "PR URL must match https://github.com/<owner>/<repo>/pull/<n>.",
        )
    owner, repo, number = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"

    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "codesensei/0.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(api_url, headers=headers)
    except httpx.TimeoutException as exc:
        raise _fail("Timed out fetching the PR diff from GitHub.") from exc
    except httpx.ConnectError as exc:
        raise _fail("Could not reach GitHub.") from exc
    except httpx.HTTPError as exc:
        raise _fail("GitHub fetch failed.") from exc

    code = response.status_code
    if code == 200:
        return response.text
    if code in (401, 403):
        raise _fail("GitHub auth failed for this PR — check the configured token.")
    if code == 404:
        raise _fail("PR not found. Check the URL and that the token has access to this repo.")
    if 500 <= code < 600:
        raise _fail("GitHub is unavailable.")
    raise _fail(f"GitHub returned HTTP {code}.")
