# Contract — `POST /api/review`

Single synchronous endpoint exposed by the FastAPI app for feature 003-pr-review-mvp. Reviews a unified diff and returns structured findings.

---

## Request

- **Method**: `POST`
- **Path**: `/api/review`
- **Headers**: `Content-Type: application/json`
- **Body** (exactly one of `diff` / `pr_url`):

```json
{ "diff": "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n" }
```

or

```json
{ "pr_url": "https://github.com/owner/repo/pull/42" }
```

Constraints:
- If both fields are present, or both are absent / null / empty string → `400 invalid_input`.
- `diff` MUST be valid UTF-8 and contain at least one diff header (`diff --git ` line, or matching `--- a/` + `+++ b/` line pair).
- `pr_url` MUST match `^https://github\.com/[^/]+/[^/]+/pull/\d+$`.
- After resolution (paste or fetch), `len(diff_bytes) <= REVIEW_MAX_DIFF_BYTES` (default 256 000). Over → `413 payload_too_large`.

---

## Success Response

- **Status**: `200 OK`
- **Body**:

```json
{
  "verdict": "request_changes",
  "findings": [
    {
      "file": "src/foo.py",
      "line": 12,
      "severity": "major",
      "message": "Possible null dereference on `user.email` — `get_user()` can return None.",
      "suggestion": "if user is None: raise NotFound(...)"
    },
    {
      "file": "src/bar.py",
      "line": null,
      "severity": "nit",
      "message": "Consider extracting the two regex literals into module-level constants."
    }
  ],
  "provider": "openai",
  "elapsed_ms": 12483
}
```

Field semantics: see `data-model.md`.

**Clean-diff case** — `200 OK` with `findings: []` and a `verdict` of `approve` or `comment`. This is **not** an error.

---

## Error Response (any non-2xx)

- **Body** (always one shape regardless of status):

```json
{
  "error": {
    "category": "payload_too_large",
    "message": "Diff exceeds the 256 KB limit. Try a smaller change.",
    "retryable": false
  }
}
```

| HTTP | `category`                  | Conditions                                                                     | `retryable` |
|-----:|-----------------------------|--------------------------------------------------------------------------------|:-----------:|
|  400 | `invalid_input`             | both-of / neither-of `diff`/`pr_url`; non-diff body; malformed PR URL          | false       |
|  413 | `payload_too_large`         | diff bytes > limit                                                             | false       |
|  502 | `github_fetch_failed`       | GitHub returned 401/403/404/5xx, or network failure                            | false       |
|  502 | `provider_unavailable`      | `ProviderError(retryable=True)` from feature 002 or `asyncio.TimeoutError`     | true        |
|  502 | `provider_malformed_output` | LLM output fails JSON parse or pydantic validation                             | false       |
|  500 | `internal`                  | unexpected exception                                                           | false       |

The default FastAPI `RequestValidationError` (422) is intercepted by an exception handler and re-emitted as `400 invalid_input` so the envelope shape is uniform.

---

## Headers in responses

- `Content-Type: application/json` always.
- No `Set-Cookie`, no per-request tracing headers added by this feature (request id is read from upstream proxy if present; otherwise generated for logs only).
- The configured `GITHUB_TOKEN` MUST NOT appear in any response header or body, ever.

---

## Idempotency / concurrency

The endpoint is **not** idempotent — each call dispatches a fresh LLM request and bills accordingly. Frontend disables the Submit button while a request is in flight (FR-016).

---

## Logging contract

Per request, exactly one structured log line at INFO level on success, one at WARNING on a known error category, and one at ERROR on `internal`. Fields:

- `event` — `"review.completed"` / `"review.failed"`
- `provider` — provider name (success only)
- `payload_bytes` — diff size (after fetch if `pr_url`)
- `finding_count` — int (success only)
- `error_category` — string (failure only)
- `elapsed_ms` — wall-clock duration

The diff body, finding bodies, PR URL path, and the GitHub token are **never** logged (FR-019, FR-011).
