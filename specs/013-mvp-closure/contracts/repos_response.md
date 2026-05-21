# Contract: `/api/repos` endpoints — feature 013 addition

**Endpoints**: `GET /api/repos`, `GET /api/repos/{id}`, `POST /api/index` (response shape)
**Source of truth**: `backend/src/codesensei/indexing/schema.py`

## `GET /api/repos` (list) + `GET /api/repos/{id}` (detail) + `POST /api/index` (response)

All three responses gain ONE optional field on the repo entity.

```json
{
  "id": "8c3c7b07-6102-4503-9802-38429381fc95",
  "source": "https://github.com/owner/repo",
  "default_branch": "main",
  "status": "ready",
  "chunk_count": 1234,
  "indexed_at": "2026-05-21T15:42:11Z",
  "last_error": null,
  "codesensei_ignore_patterns": ["vendor/", "*.generated.ts", "dist/"]
}
```

| Field | Type | Nullability | Notes |
|-------|------|-------------|-------|
| `codesensei_ignore_patterns` | `list[string]` / null | nullable | The pattern list applied at the last index run. `null` when no `.codesensei-ignore` existed (or was empty). Patterns appear in source-file order (post-truncation). |

## Backward compatibility

- All pre-feature rows return `null` for the field (no backfill — they simply weren't indexed under feature 013).
- The frontend renders the badge only when the field is non-null AND non-empty.
- Pre-feature clients that ignore unknown JSON keys keep working unchanged.

## Failure modes

- Index run fails → the field STAYS at its previous value (the row is rolled back inside the same async session).
- Index run succeeds with an oversize / corrupt ignore file → the field is set to `null` (file treated as absent per FR-005).
- Index run succeeds with > 200 patterns → the field carries the first 200 patterns (the cap is silently applied; warning is in the structured log, not on the wire).
