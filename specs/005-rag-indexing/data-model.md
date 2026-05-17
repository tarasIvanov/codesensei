# Data Model: Repo indexing + RAG-augmented review

Two new SQL tables. One new wire-shape (`ReviewRequest`/`ReviewResult` deltas). One new transient retrieval result-set object that lives only inside one request. Migrations are forward-only; on rollback the migration drops both tables (cascading drop deletes all chunks).

## Tables

### `repos`

| Column | Type | Constraint | Source |
|---|---|---|---|
| `id` | `uuid` | PK, default `gen_random_uuid()` | generated server-side |
| `source` | `text` | NOT NULL, UNIQUE | repo URL (for HTTPS) or absolute container path (for `local`) |
| `source_kind` | `text` | NOT NULL, CHECK in `('https','local')` | derived at index time |
| `default_branch` | `text` | NULL | from request body; only meaningful for `https` |
| `embedding_provider` | `text` | NULL | provider name captured at write time; NULL until chunks are written |
| `embedding_model` | `text` | NULL | model id captured at write time; NULL until chunks are written |
| `indexed_at` | `timestamptz` | NULL | set to `now()` on successful write; remains NULL while async job is pending |
| `chunk_count` | `int` | NOT NULL, default `0` | maintained by the indexing pass; never `NULL` |
| `last_error` | `text` | NULL | human-readable failure reason; cleared on next successful pass |
| `created_at` | `timestamptz` | NOT NULL, default `now()` | row birthdate; never updated |

State transitions:

```text
                ┌─────────────────┐
 POST /api/index│                 │
─────────────►  │ row inserted    │  indexed_at=NULL, chunk_count=0,
                │ (registered)    │  embedding_*=NULL
                └────────┬────────┘
                         │
              sync indexing succeeds      async job succeeds         indexing fails
                         │                         │                        │
                         ▼                         ▼                        ▼
                ┌─────────────────┐       ┌─────────────────┐      ┌─────────────────┐
                │ ready           │       │ ready           │      │ failed          │
                │ indexed_at=now  │       │ indexed_at=now  │      │ last_error=…    │
                │ chunk_count>0   │       │ chunk_count>0   │      │ chunk_count=0   │
                └────────┬────────┘       └────────┬────────┘      └────────┬────────┘
                         │                         │                        │
                  re-index passes              same                    re-index retry
                         │                         │                        │
                         ▼                         ▼                        ▼
                         (chunk_count refreshed in place; last_error cleared)
```

### `code_chunks`

| Column | Type | Constraint | Source |
|---|---|---|---|
| `id` | `uuid` | PK, default `gen_random_uuid()` | generated server-side |
| `repo_id` | `uuid` | NOT NULL, FK → `repos(id)` ON DELETE CASCADE | from the indexing pass |
| `file_path` | `text` | NOT NULL | repository-relative path with forward slashes |
| `language` | `text` | NOT NULL | one of `python | markdown | typescript | javascript | java | go | rust | cpp | c | kotlin | ruby | php | shell | yaml | toml | sql | other` |
| `start_line` | `int` | NOT NULL, CHECK `>= 1` | 1-indexed |
| `end_line` | `int` | NOT NULL, CHECK `>= start_line` | inclusive |
| `content` | `text` | NOT NULL | the raw chunk text, no truncation |
| `token_count` | `int` | NOT NULL, CHECK `>= 0` | result of `tiktoken.encoding_for_model('text-embedding-3-small').encode(content)` length at write time |
| `embedding` | `vector(1536)` | NOT NULL | produced by the configured `EmbeddingProvider` |

Indexes:

- `code_chunks_repo_id_idx` BTREE on `(repo_id)` — supports the `WHERE repo_id = ?` filter in retrieval (always paired with the HNSW search but kept separate so DELETE … WHERE repo_id = ? is fast).
- `code_chunks_embedding_hnsw_idx` HNSW on `embedding` using `vector_cosine_ops` (`<=>`).

### Migration: `003_repos_chunks`

Forward:

```sql
CREATE TABLE repos (...);
CREATE TABLE code_chunks (...);
CREATE INDEX code_chunks_repo_id_idx ON code_chunks (repo_id);
CREATE INDEX code_chunks_embedding_hnsw_idx
    ON code_chunks USING hnsw (embedding vector_cosine_ops);
```

Rollback:

```sql
DROP TABLE code_chunks;  -- HNSW index drops with the table
DROP TABLE repos;
```

The cascade on `code_chunks.repo_id` makes `DROP TABLE repos` redundant once `code_chunks` is gone, but the explicit two-step rollback is safe under either order if a partial run is retried.

## Atomic chunk replacement (FR-013)

Re-indexing must replace chunks without ever leaving the repo in a "no chunks" state. Pattern: the indexing service holds two transactions.

1. **T1** (auto-commit per batch): `INSERT INTO code_chunks (..., repo_id) VALUES …` with the **same** `repo_id` as the in-place row, but each row tagged with a `pass_id` UUID held only in memory. Crash here → orphan chunks remain attached to a partial pass; cleaned up by the next successful pass's swap step.
2. **T2** (single transaction at the very end):

   ```sql
   BEGIN;
     DELETE FROM code_chunks
      WHERE repo_id = $repo_id
        AND ctid NOT IN (SELECT ctid FROM code_chunks
                          WHERE repo_id = $repo_id
                            AND pass_id = $new_pass_id);
     UPDATE repos
        SET indexed_at = now(),
            chunk_count = (SELECT count(*) FROM code_chunks WHERE repo_id = $repo_id),
            embedding_provider = $provider,
            embedding_model = $model,
            last_error = NULL
      WHERE id = $repo_id;
   COMMIT;
   ```

3. Crash before T2 → next pass cleans up the orphan rows in its own T2.

`pass_id` is **not** persisted on `code_chunks` — instead, the indexing service inserts each row with a synthetic `content` prefix or holds the new chunk ids in memory and deletes the **complement** (`NOT IN`). For V1 we use the simpler "in-memory id list" variant: the service buffers the inserted `code_chunks.id` values from each batch's `RETURNING id` and then runs

```sql
DELETE FROM code_chunks
 WHERE repo_id = $repo_id
   AND id <> ALL ($just_inserted_ids::uuid[]);
```

inside T2. Fits on one line; no schema change needed.

## Wire-shape deltas (review API)

`ReviewRequest` gains one optional field:

```python
class ReviewRequest(BaseModel):
    diff: str | None = None
    pr_url: str | None = None
    repo_id: UUID | None = None  # NEW — opt-in to RAG
```

`ReviewResult` gains one optional field on the response (only present when `repo_id` was used):

```python
class ReviewResult(BaseModel):
    verdict: Verdict
    findings: list[Finding]
    context_files: list[str] | None = None  # NEW — list of distinct file_paths that contributed retrieved context, in score-descending order; capped at 10
```

`Finding` itself is unchanged — `context_files` is reported **per response, not per finding**, so old clients that ignore the field continue to render findings exactly as in 003/004.

## Transient: `RetrievalResultSet`

Lives only inside `ReviewService.run_for_diff(...)`. Not persisted, not exported. Fields:

- `queries: list[str]` — the per-hunk query windows derived from the diff
- `query_vectors: list[list[float]]` — embeddings of the above
- `candidates: list[ChunkHit]` where `ChunkHit = (chunk_id, repo_id, file_path, content, score, token_count)`
- `selected: list[ChunkHit]` — after dedup + token-budget trim
- `dropped: list[ChunkHit]` — chunks trimmed off; written into the `retrieval.done` log line counts only (not bodies)

`ReviewService` builds this, passes `selected` to `prompt.render(...)`, builds `context_files = [hit.file_path for hit in selected]` (deduped, preserving the first occurrence), and forgets the rest after the response is sent.

## Indexing job state (reuse 004's surface)

`index_repo_job(ctx, repo_id, source, source_kind, default_branch)` lives in `codesensei.indexing.tasks`. Status comes back through the same `lookup_job(job_id)` shape from feature 004 — no new status enum. Job result on success: `{"repo_id": "<uuid>", "chunk_count": <int>, "indexed_at": "<iso8601>"}`. Job result on failure: `{"repo_id": "<uuid>", "error": {"category": "<errcat>", "message": "<text>"}}`. Failures recorded on `repos.last_error` by the job's `finally` block before the exception propagates to arq.

## Constraints, enforced at write time

- `chunk_count > 5000` → caller refused with HTTP 413 (`payload_too_large`); no rows written.
- Two concurrent index attempts for the same `source` → second one sees the UNIQUE violation, catches it, and returns the existing `repos.id` with a 409 `already_indexing` if `indexed_at IS NULL` and `last_error IS NULL`, otherwise the sync path treats it as a re-index of the existing row.
- Embedding-provider mismatch on retrieval is enforced **read-side** in `RetrievalService.search(...)`, not at the DB layer — the `embedding_provider` / `embedding_model` columns are advisory metadata, not vectorspace-typed.
- All vectors must be exactly 1536 dimensions (`text-embedding-3-small` output). Other models (e.g. Ollama's `nomic-embed-text` at 768 dims) need a separate migration that widens the column with a new vector type; defer to a 006 feature. For V1 we hard-fail at write time if the embedding length is not 1536 — `IndexError(EMBEDDING_DIMENSION_MISMATCH, retryable=False)`.
