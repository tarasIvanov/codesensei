# Contract: `GET /api/settings/test/github`

**Feature**: 007-ui-tailwind-polish
**Status**: Draft
**Date**: 2026-05-18

Read-only probe that verifies the GitHub PAT stored in the encrypted Settings store is alive and identifies its owner. Used by `/settings` "Test connection" button. **Never** writes to GitHub; never echoes the PAT.

---

## Request

```http
GET /api/settings/test/github HTTP/1.1
Accept: application/json
```

No request body. No query parameters. No headers required from the client.

---

## Response: 200 OK (happy path)

```json
{
  "ok": true,
  "login": "codesensei-bot",
  "scopes_hint": "fine-grained",
  "elapsed_ms": 412
}
```

Field rules:
- `ok` — literal `true` (false branch is never used; failures use error envelopes).
- `login` — value of GitHub's `/user.login` field; the GitHub account the PAT belongs to.
- `scopes_hint` — verbatim value of GitHub's `X-GitHub-Token-Type` response header when present (`fine-grained`, `OAuth`, `installation`, etc.), or `null` when the header is absent.
- `elapsed_ms` — server-measured elapsed time of the outbound HTTPS call.

Forbidden fields (MUST NOT appear in any response):
- `token`, `pat`, `github_token`, `secret`, or any field carrying the PAT in any form.
- `email` (GitHub's `/user.email` may carry the PAT owner's private email — explicitly stripped).

---

## Response: error envelopes

All errors use the existing review-error envelope shape from feature 006 (`ReviewError.to_envelope()`). The probe emits a strict subset of categories.

### 503 Service Unavailable — `settings_locked`

```json
{
  "error": {
    "category": "settings_locked",
    "message": "GitHub PAT is not configured. Open Settings to add one.",
    "retryable": false
  }
}
```

Triggered when `await get_setting('GITHUB_TOKEN')` returns `None` (no PAT in store, or decryption failed).

### 401 Unauthorized — `github_auth_failed`

```json
{
  "error": {
    "category": "github_auth_failed",
    "message": "GitHub rejected the PAT (401). Check the value and required permissions.",
    "retryable": false
  }
}
```

Triggered when GitHub responds 401 or 403 to `GET /user`.

### 502 Bad Gateway — `github_api_unavailable`

```json
{
  "error": {
    "category": "github_api_unavailable",
    "message": "GitHub returned 5xx or the request timed out.",
    "retryable": true
  }
}
```

Triggered on:
- GitHub 5xx response.
- `httpx.TimeoutException`.
- `httpx.NetworkError` (DNS, connection refused, etc.).

### 429 Too Many Requests — `github_rate_limited`

```json
{
  "error": {
    "category": "github_rate_limited",
    "message": "GitHub rate-limited the probe. Retry after the indicated interval.",
    "retryable": true
  },
  "retry_after_seconds": 75
}
```

Triggered on GitHub 429. `retry_after_seconds` parses GitHub's `Retry-After` header; defaults to 60 if absent or unparseable. Lives at the top level of the envelope, not nested under `error`.

---

## Outbound call to GitHub

```http
GET https://api.github.com/user HTTP/1.1
Authorization: token <PAT>
Accept: application/vnd.github+json
User-Agent: codesensei-probe
X-GitHub-Api-Version: 2022-11-28
```

- `httpx.AsyncClient(timeout=15.0)`; **no** internal retry — the route returns the first verdict to the client and the SPA decides whether to call again.
- The probe MUST NOT send any other HTTP method to GitHub. It MUST NOT enumerate repositories, fetch user emails, or open scopes-listing endpoints.

---

## Structured log line

Exactly one structlog record per request, emitted in a `finally` block so it fires on success **and** failure paths:

```text
event=github_probe ok={true|false} login={login|null} status_code={int|null} elapsed_ms={int} category={null|<error_category>}
```

The PAT MUST NOT appear in the structured log line, the response body, the response headers, or in any error wrapper. The probe MUST NOT log `Authorization` header values.

---

## Pydantic models (backend)

```python
class SettingsTestGithubResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ok: Literal[True]
    login: str
    scopes_hint: str | None = None
    elapsed_ms: int
```

No request body model — the route accepts no payload.

---

## Frontend typed wrapper

```ts
// frontend/src/api/settings.ts
export interface TestGithubResult {
  ok: true;
  login: string;
  scopes_hint: string | null;
  elapsed_ms: number;
}

export class TestGithubError extends Error {
  constructor(
    public readonly category: string,
    message: string,
    public readonly retryable: boolean,
    public readonly retryAfterSeconds?: number,
  ) {
    super(message);
  }
}

export async function testGithub(): Promise<TestGithubResult>;
```

`testGithub` reads the top-level `retry_after_seconds` when present (parser mirrors `frontend/src/api/posting.ts`).
