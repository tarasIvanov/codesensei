# Contract: `index_repo_job` (arq)

Reuses the worker scaffolding from feature 004. One new `WorkerSettings.functions` entry; no new Redis/keys/health-check changes.

## Signature

```python
async def index_repo_job(
    ctx: dict[str, Any],
    repo_id: str,
    source: str,
    source_kind: Literal["https", "local"],
    default_branch: str | None,
) -> dict[str, Any]: ...
```

Enqueued by `POST /api/index` when the pre-scan classifies the repo as async. The HTTP handler does:

```python
job = await pool.enqueue_job("index_repo_job", repo_id, source, source_kind, default_branch)
return {"repo_id": repo_id, "job_id": job.job_id, "mode": "async"}, 202
```

## Successful result

```jsonc
{
  "repo_id": "<uuid>",
  "chunk_count": <int>,
  "indexed_at": "<iso8601 utc>",
  "embedding_provider": "<provider>",
  "embedding_model": "<model>"
}
```

Side effects:
- `repos.indexed_at = now()`, `repos.chunk_count = <new>`, `repos.embedding_provider/model = <…>`, `repos.last_error = NULL`.
- Old chunks for this `repo_id` deleted in the atomic T2 swap (see `data-model.md` §Atomic chunk replacement).

## Failure result

```jsonc
{
  "repo_id": "<uuid>",
  "error": {
    "category": "<one of: clone_failed | embedding_failed | payload_too_large | internal>",
    "message": "<human-readable>",
    "retryable": <bool>
  }
}
```

Side effects:
- `repos.last_error = <message>`, `repos.indexed_at` stays NULL (or stays at its previous value if this was a re-index — old chunks remain queryable per FR-013).
- No `code_chunks` rows from this failed pass remain — they are deleted in the job's `finally` block before the exception propagates.

## Idempotency (FR-013)

The job is idempotent **on `repo_id`**: enqueuing it twice for the same `repo_id` is safe as long as only one is "in flight" at any moment. The HTTP handler enforces "only one in flight" via the 409 `already_indexing` response on `repos.indexed_at IS NULL AND last_error IS NULL`. If a previous job died without writing `last_error` (e.g. worker OOM-killed) the row will look "stuck" — operator unblocks by `DELETE /api/repos/{id}` then re-POSTing, which is a documented manual-recovery step in `quickstart.md`.

## Cancellation

Not supported in V1. arq's `try_get_job_result(..., poll_delay=…)` returns `None` while a job is in flight; reviewers see `status: "indexing"` on the repo row until the job ends one way or the other. Killing a worker mid-job leaves the row in the "stuck" state described above.

## Job result TTL

Reuses `JOB_RESULT_TTL_S` (default 3600 from feature 004). After the TTL expires, `GET /api/jobs/{job_id}` returns 404 `not_found`. The `repos` row is the persistent record; the job id is a transient handle for UI polling.

## Health-check key

Not affected. The worker's `arq:health-check:default` heartbeat (feature 004) is independent of which functions are registered.
