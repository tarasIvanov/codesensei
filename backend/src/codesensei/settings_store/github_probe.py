"""Read-only probe for the stored GitHub PAT — feature 007.

Contract: ``specs/007-ui-tailwind-polish/contracts/settings_test_github.md``.

The probe MUST never echo the PAT in return values, log lines, or exception
messages, and MUST never make a write call to GitHub.
"""

from __future__ import annotations

import httpx

from codesensei.review.errors import ReviewError, ReviewErrorCategory

_USER_URL = "https://api.github.com/user"
_DEFAULT_RETRY_AFTER = 60


def _parse_retry_after(response: httpx.Response) -> int:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return _DEFAULT_RETRY_AFTER
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_RETRY_AFTER


async def probe_github(token: str) -> dict[str, str | None]:
    """Call GitHub ``GET /user`` and return ``{login, scopes_hint}`` on success.

    Raises ``ReviewError`` on any failure, mapped per the contract.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
        "User-Agent": "codesensei-probe",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(_USER_URL, headers=headers)
    except httpx.TimeoutException as exc:
        raise ReviewError(
            ReviewErrorCategory.GITHUB_API_UNAVAILABLE,
            "GitHub probe timed out.",
            retryable=True,
        ) from exc
    except httpx.HTTPError as exc:
        raise ReviewError(
            ReviewErrorCategory.GITHUB_API_UNAVAILABLE,
            "GitHub probe failed (network).",
            retryable=True,
        ) from exc

    status = response.status_code
    if status == 200:
        try:
            body = response.json()
        except ValueError as exc:
            raise ReviewError(
                ReviewErrorCategory.GITHUB_API_UNAVAILABLE,
                "GitHub returned a non-JSON body to /user.",
                retryable=True,
            ) from exc
        login = body.get("login")
        if not isinstance(login, str):
            raise ReviewError(
                ReviewErrorCategory.GITHUB_API_UNAVAILABLE,
                "GitHub /user response missing 'login'.",
                retryable=True,
            )
        scopes_hint = response.headers.get("X-GitHub-Token-Type")
        return {"login": login, "scopes_hint": scopes_hint}

    if status in (401, 403):
        raise ReviewError(
            ReviewErrorCategory.GITHUB_AUTH_FAILED,
            f"GitHub rejected the PAT ({status}). Check the value and required permissions.",
        )
    if status == 429:
        raise ReviewError(
            ReviewErrorCategory.GITHUB_RATE_LIMITED,
            "GitHub rate-limited the probe. Retry after the indicated interval.",
            retryable=True,
            retry_after_seconds=_parse_retry_after(response),
        )
    if 500 <= status < 600:
        raise ReviewError(
            ReviewErrorCategory.GITHUB_API_UNAVAILABLE,
            f"GitHub returned {status}.",
            retryable=True,
        )

    raise ReviewError(
        ReviewErrorCategory.GITHUB_API_UNAVAILABLE,
        f"GitHub returned unexpected status {status}.",
        retryable=True,
    )
