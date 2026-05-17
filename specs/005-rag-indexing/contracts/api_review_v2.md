# Contract: POST /api/review (v2 — RAG-aware)

Delta against 003+004. Backward-compatible: callers that omit `repo_id` get exactly the 004 behaviour.

## Request

```jsonc
{
  "diff": "diff --git a/billing.py b/billing.py\n…",     // OR
  "pr_url": "https://github.com/owner/repo/pull/123",   // exactly one of diff|pr_url required (unchanged from 003)
  "repo_id": "8e1c9a3b-…"                                // NEW, optional UUID
}
```

Validation:
- Unchanged precondition: exactly one of `diff` / `pr_url`.
- `repo_id` (if present): MUST be a valid UUID4. Unknown id → 400 `invalid_input` with message `"Unknown repo_id=<id>"`; no LLM call.
- `repo_id` present + repo's `indexed_at IS NULL` → 409 `repo_not_ready` with `retryable: true`.
- `repo_id` present + repo's embedding provider/model differs from the currently configured one → 422 `embedding_mismatch` with message naming both sides; no LLM call.

## Response — `repo_id` absent

Byte-equivalent to 003+004 response. No `context_files` field at all (not even `null`).

```jsonc
{
  "verdict": "approve | request_changes | comment",
  "findings": [ … ]
}
```

## Response — `repo_id` present

Adds one field on top of the 003+004 response:

```jsonc
{
  "verdict": "…",
  "findings": [ … ],
  "context_files": [
    "src/billing/checkout.py",
    "src/billing/__init__.py",
    "docs/architecture/billing.md"
  ]
}
```

`context_files` rules:
- Distinct file paths that contributed at least one chunk to the retrieved-context block injected into the LLM prompt.
- Ordered by descending best score across the chunks of that file.
- Maximum length: 10 (defensive cap; the actual list is rarely longer because of the 3 000-token budget).
- May be empty (`[]`) if retrieval produced no matches above the floor, in which case the LLM was called without a retrieved-context block but `context_files` is still present (to distinguish "RAG was requested but found nothing" from "RAG was not requested at all").

## Status-code map

| Path | Status | Category |
|---|---|---|
| Happy (with or without `repo_id`) | 200 | — |
| Bad input shape | 400 | `invalid_input` |
| Unknown `repo_id` | 400 | `invalid_input` |
| `repo_id` points at a repo whose async indexing is still pending | 409 | `repo_not_ready` |
| Embedding provider/model mismatch | 422 | `embedding_mismatch` |
| Payload too large (diff > limit) | 413 | `payload_too_large` (unchanged from 003) |
| GitHub fetch failed | 502 | `github_fetch_failed` (unchanged from 003) |
| LLM provider unavailable | 502 | `provider_unavailable` (unchanged) |
| LLM output malformed | 502 | `provider_malformed_output` (unchanged) |
| Settings locked (003's category — unchanged) | 503 | `settings_locked` |
| Internal | 500 | `internal` |

## Observability

When `repo_id` is set, exactly **two** log lines fire per request (in addition to the existing 003 `review.complete` line):

1. `retrieval.started repo_id=… queries=<int>`
2. `retrieval.done repo_id=… chunks_fetched=<int> chunks_used=<int> trimmed=<int> empty=<bool>`

No chunk content is logged. No prompt content is logged (003 already enforces this).
