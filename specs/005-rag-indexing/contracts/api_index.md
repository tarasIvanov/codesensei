# Contract: Indexing & registry endpoints

All endpoints under prefix `/api`.

## POST /api/index

Submit a repository for indexing. Sync for ≤200 source-file repos, async for larger.

### Request

```jsonc
{
  "source": "https://github.com/example/repo.git",   // OR an absolute container path "/mnt/local/repo"
  "default_branch": "main"                            // optional, ignored for "local"
}
```

Validation:
- `source` MUST be non-empty.
- `source` starting with `https://` → `source_kind = "https"`. Any other absolute filesystem path → `source_kind = "local"`. SSH URLs (`git@…`) → 400 `invalid_input` (deferred per Assumptions).
- `default_branch` optional, ignored when `source_kind == "local"`.

### Responses

| Path | Status | Body shape |
|---|---|---|
| Sync success (≤200 source files) | 201 Created | `{"repo_id": "<uuid>", "chunk_count": <int>, "indexed_at": "<iso8601 utc>", "mode": "sync"}` |
| Async accepted (>200 source files) | 202 Accepted | `{"repo_id": "<uuid>", "job_id": "<arq job id>", "mode": "async"}` |
| Pre-scan exceeds 5000-chunk cap | 413 Payload Too Large | `{"error": {"category": "payload_too_large", "message": "Repository would produce N chunks; the per-repo cap is 5000.", "retryable": false}}` |
| Same source already indexing | 409 Conflict | `{"error": {"category": "already_indexing", "message": "Indexing already in progress for source=…", "retryable": true}, "repo_id": "<uuid>"}` |
| Clone failure | 502 Bad Gateway | `{"error": {"category": "clone_failed", "message": "Could not clone <source>: <git stderr first line>", "retryable": true}}` |
| Queue unavailable (async path only) | 502 | `{"error": {"category": "queue_unavailable", "message": "…", "retryable": true}}` |
| Bad source | 400 | `{"error": {"category": "invalid_input", "message": "…", "retryable": false}}` |
| Internal | 500 | `{"error": {"category": "internal", "message": "An internal error occurred.", "retryable": true}}` |

### Side effects

- On success (sync or async start): a `repos` row exists with the canonical `source` (URL-normalised: trailing `.git` stripped, trailing `/` stripped) and `created_at = now()`.
- On sync success: `chunk_count > 0`, `indexed_at` set, `embedding_provider`/`embedding_model` set.
- On async start: `chunk_count = 0`, `indexed_at = NULL`, `embedding_*` NULL. The arq job fills these on completion.
- On any failure: `repos.last_error` is set; if the row is new (created by this request) it is **deleted** rather than left as a tombstone, because callers retry by re-POSTing.

## GET /api/repos

List all repositories.

### Response 200 OK

```jsonc
{
  "repos": [
    {
      "repo_id": "…",
      "source": "https://github.com/example/repo.git",
      "source_kind": "https",
      "default_branch": "main",
      "indexed_at": "2026-05-17T18:00:00Z",   // null while async pending
      "chunk_count": 487,
      "embedding_provider": "openai",
      "embedding_model": "text-embedding-3-small",
      "status": "ready",                       // one of: ready | indexing | failed
      "last_error": null
    },
    …
  ]
}
```

Ordering: `indexed_at DESC NULLS LAST, created_at DESC`. Empty registry → `{"repos": []}` (still 200).

`status` is derived:
- `indexed_at IS NOT NULL` → `"ready"`
- `indexed_at IS NULL AND last_error IS NULL` → `"indexing"`
- `indexed_at IS NULL AND last_error IS NOT NULL` → `"failed"`

## DELETE /api/repos/{repo_id}

Remove a repository and all its chunks.

### Responses

| Path | Status | Body |
|---|---|---|
| Deleted | 204 No Content | empty |
| Unknown id | 404 | `{"error": {"category": "not_found", "message": "No repo with id=…", "retryable": false}}` |
| In-flight indexing | 409 | `{"error": {"category": "delete_during_index", "message": "Cannot delete while indexing is in progress.", "retryable": true}}` |

Implementation:
- Cascade ON DELETE on `code_chunks` removes all chunks atomically with the row deletion.
- 409 path checks for an unfinished arq job (`repos.indexed_at IS NULL AND last_error IS NULL`) and refuses; users can re-DELETE after the job ends one way or the other.

## Error envelope

Reuses the 003/004 envelope:

```jsonc
{ "error": { "category": "<string>", "message": "<string>", "retryable": <bool> } }
```

New categories introduced by this endpoint family:
- `payload_too_large` (413; reused name, indexing-specific message)
- `already_indexing` (409)
- `clone_failed` (502)
- `delete_during_index` (409)
- `embedding_dimension_mismatch` (500 — surfaces if an EmbeddingProvider returns a vector that isn't 1536d)
- `embedding_failed` (502 — EmbeddingProvider raises during the indexing pass)
- `queue_unavailable` (502; reused from 004)

All existing categories from 003/004 remain valid.
