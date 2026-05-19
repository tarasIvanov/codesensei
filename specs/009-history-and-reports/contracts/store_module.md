# Contract: `reviews_history/store.py`

Public surface of the persistence module. Five async functions + one module constant. No singletons, no global state.

## Module-level constants

```python
_HISTORY_MAX_ROWS = 1000
_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 200
```

Private (leading underscore); not env-exposed in v1 (Out of Scope §).

## Public functions

### `async def insert_run(session, *, ...) -> ReviewRun`

```python
async def insert_run(
    session: AsyncSession,
    *,
    input_kind: Literal["diff", "pr_url"],
    pr_url: str | None,
    repo_id: UUID | None,
    diff: str,
    verdict: str,
    provider: str,
    elapsed_ms: int,
    findings: Sequence[Finding],   # review/schema.py
    context_files: list[str] | None,
) -> ReviewRun:
```

Behaviour:
- Inserts one `review_runs` row + N `review_findings` rows (one per finding, with `position` set to the original index in the input sequence).
- Returns the inserted `ReviewRun` ORM instance (with `findings` lazily loadable).
- Sets `has_temporal = any(f.temporal_context for f in findings)`.
- Sets `finding_count = len(findings)`.
- Commits the session BEFORE returning — callers do NOT need to commit.
- Raises on any DB error — caller wraps in try/except (see `review/service.py` integration).

### `async def list_runs(session, *, limit: int = 50) -> list[ReviewRun]`

Returns the N most-recent `ReviewRun` instances (no `findings` joined — list view does not need them).

- `limit` is clamped to `_MAX_LIST_LIMIT = 200`; values < 1 are clamped to `_DEFAULT_LIST_LIMIT = 50`.
- Ordered by `created_at DESC, id DESC` (the second key breaks ties on identical microsecond timestamps).
- Uses the `review_runs_created_at_id_idx` index for a single index scan.

### `async def fetch_run(session, run_id: UUID) -> ReviewRun | None`

Returns the `ReviewRun` matching `run_id`, with its `findings` eager-loaded ordered by `position ASC`. Returns `None` when not found.

### `async def delete_run(session, run_id: UUID) -> bool`

Deletes the run + all its findings (CASCADE). Returns `True` on success, `False` if `run_id` did not exist. Commits before returning.

### `async def prune_to_cap(session) -> int`

Enforces `_HISTORY_MAX_ROWS`. Returns the number of rows deleted (0 when count ≤ cap).

```sql
DELETE FROM review_runs
 WHERE id IN (
   SELECT id FROM review_runs
    ORDER BY created_at ASC
    LIMIT :overflow
 )
```

Where `:overflow = max(0, count(*) - _HISTORY_MAX_ROWS)`. Commits before returning.

## Invariants

Verifiable in unit tests:

1. **Cap enforcement** — `prune_to_cap` after inserting `_HISTORY_MAX_ROWS + 1` rows leaves exactly `_HISTORY_MAX_ROWS` rows.
2. **FK cascade on delete** — `delete_run(rid)` removes both the run and its findings; no orphaned findings remain.
3. **FK SET NULL on repo delete** — deleting a repo via `repos_store.delete_repo` leaves the `review_runs.repo_id` for that repo at `NULL`; the run survives.
4. **Position-stable ordering** — `fetch_run` returns findings in insertion order regardless of insertion timing.
5. **`has_temporal` truthiness** — `insert_run` with at least one finding carrying a non-empty `temporal_context` produces a row with `has_temporal = True`; otherwise `False`.

## Structured-logging contract

`insert_run` and `prune_to_cap` are silent on the happy path (the caller logs `review_persisted` from `review/service.py`). On unexpected DB errors, callers log `review_persist_failed` with `reason=str(exc)[:200]`.

## What `store.py` does NOT do

- No HTTP-shape pydantic validation — that lives in `reviews_history/api.py`.
- No retention configuration via env var (Out of Scope §).
- No background scheduling — the prune step is sync from the caller's perspective (just `await`ed once after `insert_run`).
- No multi-row insert via raw SQL — uses the SQLAlchemy 2.x async ORM throughout (matches the established pattern in `indexing/store.py`).
