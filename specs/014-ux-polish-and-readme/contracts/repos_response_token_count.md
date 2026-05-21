# Contract: `/api/repos` response — feature 014 addition

**Endpoints**: `GET /api/repos`, `POST /api/index` (response shape)
**Source of truth**: `backend/src/codesensei/indexing/service.py:_serialise_repo`

## Existing fields (unchanged)

```json
{
  "repo_id": "8c3c7b07-6102-4503-9802-38429381fc95",
  "source": "https://github.com/owner/repo",
  "source_kind": "https",
  "default_branch": "main",
  "indexed_at": "2026-05-21T15:42:11Z",
  "chunk_count": 234,
  "embedding_provider": "openai",
  "embedding_model": "text-embedding-3-small",
  "status": "ready",
  "last_error": null,
  "codesensei_ignore_patterns": ["vendor/"]
}
```

## New field (added by feature 014)

```json
{
  "embedding_token_count": 1234567
}
```

| Field | Type | Notes |
|-------|------|-------|
| `embedding_token_count` | integer | `SUM(code_chunks.token_count)` for this repo's currently-persisted chunks. `0` when the repo has zero chunks. Always present after feature 014 ships; frontend treats absence as `0` for backward-compat. |

## Backward compatibility

- All pre-feature persisted rows return correct sums because `code_chunks.token_count` has been populated since feature 005 / ADR-007.
- The frontend type marks the field optional and renders `??  0` so a frontend running against a pre-014 backend degrades to `0 tokens` rather than `undefined`.
- No DB schema change. No migration required.

## Aggregate query

Conceptual SQL:

```sql
SELECT repo_id, SUM(token_count) AS total
FROM code_chunks
WHERE repo_id = ANY(:ids)
GROUP BY repo_id;
```

Executed once per `GET /api/repos` call. Result joined into the in-memory list at the service layer; missing repos default to `0`.

## Failure modes

- DB unreachable → existing `GET /api/repos` already 5xx's at the session-acquire step. The new aggregate inherits the same failure surface; no new category introduced.
- Repo with zero chunks → response carries `embedding_token_count: 0` (not null, not absent).
