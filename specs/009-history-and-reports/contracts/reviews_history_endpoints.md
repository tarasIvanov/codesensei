# Contract: `/api/reviews` endpoints

Three new endpoints under the existing `/api/` prefix. All authorisation matches the rest of the API (single-user self-hosted, no auth layer in v1).

## `GET /api/reviews`

List the most-recent stored review runs.

### Request

- Method: `GET`
- Path: `/api/reviews`
- Query: `limit` (optional, integer, `1 ≤ limit ≤ 200`, default `50`).

### Response 200

```jsonc
{
  "runs": [
    {
      "id": "f3a8c9d2-7e1b-4c5d-9f8a-1b2c3d4e5f6a",
      "created_at": "2026-05-19T18:42:13+00:00",
      "input_kind": "pr_url",
      "pr_url": "https://github.com/octokit/octokit.js/pull/123",
      "verdict": "request_changes",
      "provider": "openai",
      "elapsed_ms": 4231,
      "finding_count": 7,
      "has_temporal": true
    },
    { /* ... up to `limit` rows ... */ }
  ]
}
```

Ordered by `created_at DESC`. The array is empty (`{"runs": []}`) when nothing is stored. Wraps in a top-level object so future fields (next-cursor, totals) can land additively.

### Response 4xx

- `400` if `limit` is outside `1..200` — standard `ReviewError` envelope with `category="invalid_input"`.

### Latency

- ≤ 30 ms p95 on a typical host (single index scan on `review_runs_created_at_id_idx`).

## `GET /api/reviews/{run_id}`

Reconstruct the full review payload for a stored run.

### Request

- Method: `GET`
- Path: `/api/reviews/{run_id}` where `run_id` is a UUID.

### Response 200

```jsonc
{
  "id": "f3a8c9d2-…",
  "created_at": "2026-05-19T18:42:13+00:00",
  "input_kind": "pr_url",
  "pr_url": "https://github.com/octokit/octokit.js/pull/123",
  "diff": "diff --git a/src/...\n@@ -1,3 +1,3 @@\n...",
  "verdict": "request_changes",
  "provider": "openai",
  "elapsed_ms": 4231,
  "findings": [
    {
      "file": "src/auth.ts",
      "line": 47,
      "severity": "major",
      "message": "Token refresh race condition.",
      "suggestion": "Wrap refresh in a per-user mutex.",
      "temporal_context": [ { "commit_sha": "abc1234...", "short_sha": "abc1234", "author_email": "alice@x", "author_date": "2026-01-15T10:42:13+00:00", "subject": "Fix race", "hunk_lines_changed": 7 } ]
    },
    { /* ... ordered by stored position ASC ... */ }
  ],
  "context_files": ["src/auth.ts", "src/auth_provider.ts"]
}
```

`findings` re-uses the same `Finding` pydantic shape returned by `POST /api/review` (FR-007). Field-level rules:

- `findings[].temporal_context` is `null` when no entries were attached; `[]` is normalised to `null` server-side.
- `context_files` is `null` when no RAG retrieval happened on the original run.
- `diff` is the verbatim normalised diff text, capped at the original 200 KB review-size limit.

### Response 4xx

- `404` if the `run_id` does not exist — `ReviewError` envelope `category="invalid_input"` with `message="Review run not found."`.

### Latency

- ≤ 50 ms p95 on a typical host (PK lookup + bounded child scan).

## `DELETE /api/reviews/{run_id}`

Remove a stored run and all its findings.

### Request

- Method: `DELETE`
- Path: `/api/reviews/{run_id}`

### Response 204

Empty body. Idempotent on the second call — see 404 below.

### Response 4xx

- `404` if the `run_id` does not exist — `ReviewError` envelope `category="invalid_input"` with `message="Review run not found."`. Deleting an already-deleted run returns 404 on the second call.

### Latency

- ≤ 30 ms p95 on a typical host (PK lookup + CASCADE delete).

## Retention semantics

Pruning is NOT a public endpoint — it runs automatically:

1. **At process startup** (one-shot) — before the API marks itself ready. Trims any historical excess beyond `_HISTORY_MAX_ROWS = 1000` rows. Bounded by the `(created_at DESC, id)` index scan.
2. **Inline after every successful persist** — after `INSERT INTO review_runs` returns, the prune step runs in the same async session. If the count is at or below the cap, this is a no-op.

Prune failure does NOT bubble to the caller. The next successful persist or startup will retry.

## Error envelope

Re-uses the existing `ReviewError` envelope shape from feature 003:

```jsonc
{
  "error": {
    "category": "invalid_input",
    "message": "Review run not found.",
    "retryable": false
  }
}
```

No new error categories are introduced.

## What this contract does NOT promise

- No `GET /api/reviews?since=<timestamp>` cursor pagination (out of scope).
- No full-text search via `GET /api/reviews?q=<...>` (out of scope).
- No `PATCH /api/reviews/{run_id}` — stored runs are immutable beyond delete.
- No re-post / re-run endpoints — those flow through the existing `POST /api/review/post` and `POST /api/review`.
- No webhook hook on persist.
