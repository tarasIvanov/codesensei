# Contract: `/api/review/run` response (additive change)

Documents the wire-shape delta on the existing `POST /api/review/run` endpoint. No URL changes, no header changes, no error-envelope changes.

## Response shape (additive)

The existing response is a `ReviewResult` object whose `findings` array contains zero or more `Finding` objects. This feature appends one optional field to `Finding`:

```jsonc
{
  "verdict": "comment",
  "findings": [
    {
      "file": "src/auth/middleware.py",
      "line": 47,
      "severity": "major",
      "message": "Token refresh race introduced.",
      "suggestion": "Wrap refresh in a per-user asyncio.Lock.",
      "temporal_context": [                          // ⬅ NEW (optional)
        {
          "commit_sha": "abc1234567890abcdef1234567890abcdef12345",
          "short_sha": "abc1234",
          "author_email": "alice@example.org",
          "author_date": "2026-01-15T10:42:13+00:00",
          "subject": "Fix race in token refresh path",
          "hunk_lines_changed": 7
        },
        {
          "commit_sha": "def5678....",
          "short_sha": "def5678",
          "author_email": "bob@example.org",
          "author_date": "2025-11-02T18:01:55+00:00",
          "subject": "Add idempotency guard around POST /refresh",
          "hunk_lines_changed": 3
        }
      ]
    },
    {
      "file": "src/util/format.py",
      "line": 12,
      "severity": "nit",
      "message": "Inconsistent quoting style.",
      "suggestion": null,
      "temporal_context": null                       // ⬅ NEW: absent when no history matched
    }
  ],
  "provider": "openai",
  "elapsed_ms": 1840,
  "context_files": ["src/auth/middleware.py"]
}
```

### Field rules

- `temporal_context` is **omitted or `null`** for findings without a matching line window (no entries, no match, or `finding.line` was `null`).
- When present, `temporal_context` is a JSON array of 1–5 entries (FR-002), in descending order of `author_date` (newest first).
- Each entry's fields are non-empty strings (or a non-negative integer for `hunk_lines_changed`), as defined in `data-model.md`.
- The whole field is omitted from `Finding` pydantic dumps via `model_dump(exclude_none=True)` to keep the payload minimal.
- A pre-feature client that does not know about `temporal_context` parses the response unchanged (FR-022).

## Diff-only path

For requests **without** `repo_id` (diff-only mode):

- No temporal collection runs.
- No `temporal_fetch` log entry is emitted.
- The response shape is byte-identical to the pre-feature shape: `temporal_context` is absent on every finding (`exclude_none=True`).

## Error-envelope contract

This feature **does not** introduce new error categories. All temporal failures are absorbed inside `git_temporal.py` per FR-019 and return as empty arrays, never as `ReviewError` envelopes.

## Latency contract

- Reviews **with** `repo_id` complete within `(pre-feature latency) + 2.0 s` (SC-003).
- Reviews **without** `repo_id` complete within `pre-feature latency + 0 s` (SC-004).
- Second consecutive review against the same `repo_id` on the same container completes its temporal phase in ≤ 50% of the first run's temporal phase (SC-005).
