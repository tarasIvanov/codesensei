# Contract: `POST /api/review/post`

Closes ADR-006 implementation. Publishes a previously-rendered `ReviewResult` to a GitHub PR as one native review.

## Request

`Content-Type: application/json`

```json
{
  "review_result": {
    "verdict": "request_changes",
    "findings": [
      {"file": "src/auth.py", "line": 42, "severity": "blocker", "message": "SQL built with f-string.", "suggestion": "Use parameterised query."}
    ],
    "provider": "openai",
    "elapsed_ms": 4218,
    "context_files": ["src/auth.py", "src/db.py"]
  },
  "pr_url": "https://github.com/owner/repo/pull/42",
  "event": "REQUEST_CHANGES"
}
```

Validation:

- `review_result` must validate against the existing `ReviewResult` model (feature 003+005). Unknown fields are ignored; missing required fields → 400 with category `invalid_input`.
- `pr_url` must match `^https://github\.com/[^/\s]+/[^/\s]+/pull/\d+$`. Malformed → 400 `invalid_input`. No outbound HTTP attempted.
- `event` is `Literal["COMMENT", "REQUEST_CHANGES", "APPROVE"]`. Any other value → 400 `invalid_input`. Server applies no default; the frontend pre-fills it from the verdict.
- Pydantic config `extra="forbid"` — extra keys → 400.

## Success response — 200

```json
{
  "review_id": 2417882415,
  "html_url": "https://github.com/owner/repo/pull/42#pullrequestreview-2417882415",
  "posted_at": "2026-05-17T14:33:01Z",
  "comment_count": 1,
  "attempted_calls": 1
}
```

- HTTP 200 (not 201). The created GitHub review *is* a new resource, but our endpoint is a proxy — 200 reflects "your request succeeded" rather than "we created a new local entity".
- `comment_count` is the *posted* inline-comment count, after the 50-cap and any 422-fallback. Zero is legal (body-only review).
- `attempted_calls`: 1 happy path, 2 when the body-only fallback ran.
- Response carries no token. Response carries no chunk content. Response carries no diff content.

## Error responses

All errors follow the existing `ReviewError.to_envelope()` shape:

```json
{"error": {"category": "<value>", "message": "<human>", "retryable": <bool>}}
```

`github_rate_limited` additionally carries `retry_after_seconds` at the envelope level:

```json
{
  "error": {"category": "github_rate_limited", "message": "GitHub returned 429.", "retryable": true},
  "retry_after_seconds": 60
}
```

| Category | HTTP | Trigger | Retryable |
|----------|:----:|---------|:---------:|
| `invalid_input` | 400 | `pr_url` malformed, `event` outside enum, `review_result` fails schema validation. | false |
| `settings_locked` | 503 | `app_settings.GITHUB_TOKEN` is missing or fails to decrypt. | false |
| `github_auth_failed` | 401 | GitHub responded 401 or 403. Message must name the GitHub permission the bot is missing (`pull_requests:write` for the canonical case). | false |
| `github_pr_not_found` | 404 | GitHub responded 404. | false |
| `github_review_rejected` | 502 | GitHub responded 422 after the body-only fallback, OR responded 422 on the first attempt with a non-position structural error (e.g. invalid `event` value — unreachable from a well-validated request, but defended against). Message contains GitHub's raw error body verbatim. | false |
| `github_api_unavailable` | 502 | GitHub responded 5xx, the request timed out, or the network failed. | true |
| `github_rate_limited` | 429 | GitHub responded 429. Envelope carries `retry_after_seconds`. | true |
| `internal` | 500 | Anything unexpected (bug). | false |

## Forbidden response fields

The endpoint MUST NOT emit any of the following in any response (success or error):

- `GITHUB_TOKEN` value (full or redacted)
- The decrypted Fernet plaintext of any other secret
- The original `review_result` echoed back (it is the input; echoing wastes bytes)
- The raw GitHub response body for any successful call (we only echo our derived fields)

The `github_review_rejected` message *does* carry GitHub's raw error body — by design, because the operator needs it to debug a structural rejection.

## Structured log line

Emitted once per attempted post, success or failure:

```
github_review_posted
  pr_url=https://github.com/owner/repo/pull/42
  event=REQUEST_CHANGES
  comment_count=1
  body_chars=412
  elapsed_ms=842
  review_id=2417882415         # null on failure
  outcome=ok                   # or the failure category
  attempted_calls=1
```

Emitted via `structlog.get_logger().info("github_review_posted", ...)`. The PAT is never logged. The review body content is never logged.

## Examples — full envelopes

### Success

```http
POST /api/review/post HTTP/1.1
Content-Type: application/json

{"review_result": {...}, "pr_url": "...", "event": "COMMENT"}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"review_id": 2417882415, "html_url": "...", "posted_at": "2026-05-17T14:33:01Z", "comment_count": 3, "attempted_calls": 1}
```

### 422 with body-only fallback succeeding (still 200 to client)

GitHub returns 422 with `"Line 42 in src/auth.py is not part of the pull request diff"` on the first POST. The service retries once with `comments: []` and GitHub returns 200. The client sees:

```http
HTTP/1.1 200 OK
{"review_id": 2417882416, "html_url": "...", "posted_at": "...", "comment_count": 0, "attempted_calls": 2}
```

### Settings locked

```http
HTTP/1.1 503 Service Unavailable
{"error": {"category": "settings_locked", "message": "No GitHub bot token configured. Open Settings to add one.", "retryable": false}}
```

### Rate limited

```http
HTTP/1.1 429 Too Many Requests
{
  "error": {"category": "github_rate_limited", "message": "GitHub returned 429.", "retryable": true},
  "retry_after_seconds": 60
}
```
