# Contract — GitHub PR Diff Fetch

How `backend/src/codesensei/review/github_diff.py` resolves a GitHub PR URL into a unified diff string. Single-purpose module; no other code in this feature talks to GitHub.

---

## Input

A `pr_url` already validated against `^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$`. The three captured groups are the GitHub `owner`, `repo`, and PR `number`.

---

## Outbound HTTP request

- **Method**: `GET`
- **URL**: `https://api.github.com/repos/{owner}/{repo}/pulls/{number}`
- **Headers** (always):
  - `Accept: application/vnd.github.v3.diff`
  - `User-Agent: codesensei/0.0`
  - `X-GitHub-Api-Version: 2022-11-28`
- **Headers** (when `settings.github_token` is non-empty):
  - `Authorization: Bearer {settings.github_token}`
- **Timeout**: `httpx.AsyncClient(timeout=10.0)`.

---

## Response handling

| GitHub response          | Module behaviour                                                          |
|--------------------------|---------------------------------------------------------------------------|
| `200 OK`, body = diff    | Return `response.text` to the caller. No further parsing.                 |
| `401` / `403`            | Raise `ReviewError(github_fetch_failed, "GitHub auth failed for this PR — check the configured token.", retryable=False)` |
| `404`                    | Raise `ReviewError(github_fetch_failed, "PR not found. Check the URL and that the token has access to this repo.", retryable=False)` |
| `5xx`                    | Raise `ReviewError(github_fetch_failed, "GitHub is unavailable.", retryable=False)` (note: not retryable at the API level — user can retry manually) |
| `httpx.TimeoutException` | Raise `ReviewError(github_fetch_failed, "Timed out fetching the PR diff from GitHub.", retryable=False)` |
| `httpx.ConnectError`     | Raise `ReviewError(github_fetch_failed, "Could not reach GitHub.", retryable=False)` |

---

## What the module MUST NOT do

- MUST NOT log the value of `Authorization` header or `settings.github_token`.
- MUST NOT include the token (or any header) in the raised `ReviewError.message`.
- MUST NOT follow redirects to non-github.com hosts (default `httpx` policy — `follow_redirects=False` — is sufficient and we keep it that way).
- MUST NOT cache responses across requests (per FR-018, no persistence).
- MUST NOT support GitHub Enterprise hosts in this MVP. URLs not matching the canonical `github.com` shape are rejected upstream in request validation.

---

## Test surface (`tests/unit/test_github_diff.py`)

Using `respx`:

| Test                                 | Mock                          | Expectation                                                  |
|--------------------------------------|-------------------------------|--------------------------------------------------------------|
| `test_fetch_happy`                   | 200 + diff body               | Returns diff string verbatim.                                |
| `test_fetch_sends_auth_when_token`   | 200, assert request           | Request carried `Authorization: Bearer …` header.            |
| `test_fetch_omits_auth_when_no_token`| 200, assert request           | Request had no `Authorization` header.                       |
| `test_fetch_401`                     | 401                           | Raises `ReviewError(github_fetch_failed)`; message has no token. |
| `test_fetch_404`                     | 404                           | Raises `ReviewError(github_fetch_failed)`; "not found" wording. |
| `test_fetch_500`                     | 500                           | Raises `ReviewError(github_fetch_failed)`.                   |
| `test_fetch_timeout`                 | `httpx.TimeoutException`      | Raises `ReviewError(github_fetch_failed)`.                   |
| `test_fetch_connect_error`           | `httpx.ConnectError`          | Raises `ReviewError(github_fetch_failed)`.                   |
| `test_fetch_never_logs_token`        | 200, capture logs             | No log line contains the token value.                        |

All tests offline (respx). No real GitHub call.
