# Data Model: MVP closure — custom-ignore + live index progress

**Feature**: 013-mvp-closure
**Date**: 2026-05-21

Defines the persistent + in-memory entities introduced or extended by feature 013. All shape decisions derive from `spec.md` and `research.md`.

---

## Entity 1 — `IgnoreSpec` (in-memory dataclass)

The parsed contents of one `.codesensei-ignore` file. Lifetime: one index run.

**Location**: `backend/src/codesensei/indexing/ignore.py`

**Shape** (frozen dataclass):

| Field | Type | Notes |
|-------|------|-------|
| `patterns` | `tuple[str, ...]` | Source-order list of normalised glob strings (trailing `/` stripped, trailing whitespace trimmed, blanks/comments dropped). |
| `directory_flags` | `tuple[bool, ...]` | Parallel array; `True` when the source line ended with `/`. Same length as `patterns`. |
| `warnings` | `tuple[str, ...]` | Structured warning keys emitted during parse (`"codesensei_ignore_truncated"`, `"codesensei_ignore_oversize"`). Empty tuple on a clean parse. |

**Lifecycle**: constructed once by `parse_ignore_file(root: Path) -> IgnoreSpec | None` at the start of each index run. `None` when the file does not exist. Passed through `iter_source_files()` via `extra_skip_globs=spec.patterns` (the `IgnoreSpec` shape is the public type; the chunker only consumes the patterns list + a helper that knows the directory flags).

**Invariants**:

- `len(patterns) == len(directory_flags)`.
- `len(patterns) <= 200` (hard cap from FR-004).
- Each `pattern` is non-empty after normalisation.
- `directory_flags[i] == True` ⟹ the source line ended with a literal `/`.

---

## Entity 2 — `repos` row (extended Postgres table)

Persistent shape of an indexed repository. Existing columns from feature 005 unchanged.

**New columns** (alembic revision `006_repos_codesensei_ignore.py`):

| Column | SQL type | Null? | Notes |
|--------|----------|-------|-------|
| `codesensei_ignore_patterns` | `JSONB` | YES | The parsed pattern list applied at the last index run, in source order. `NULL` when no file existed; an empty JSON array `[]` is NEVER stored (an effectively-empty file is treated as absent per the edge-case decision in `spec.md`). |

**Migration policy**:

- Single `op.add_column` call. `nullable=True`. No backfill — every existing row stays `NULL` until its next re-index.
- Downgrade: one `op.drop_column` call.
- No new index — the column is read on `GET /api/repos`, not filtered against.

**ORM mirror**: `indexing/models.py:Repo` gains `codesensei_ignore_patterns: Mapped[list[str] | None]` with `JSONB` column type.

**Write semantics**:

- Written by `_run_index_inline` and `index_repo_job` AFTER the chunk-store swap commits, inside the same async session so the column update is durably co-committed with the index outcome.
- On parse failure / file missing → write `NULL` (not `[]`).
- On parse success with ≥ 1 pattern → write the pattern list as a JSON array of strings.

---

## Entity 3 — `RepoSummary` / `RepoDetail` (extended pydantic models)

Wire shapes of `GET /api/repos` (list) and `GET /api/repos/{id}` (detail).

**Location**: `backend/src/codesensei/indexing/schema.py`

Both models gain ONE new optional field:

| Field | Type | Notes |
|-------|------|-------|
| `codesensei_ignore_patterns` | `list[str] \| None` | Mirrors the persisted column. `None` when no ignore file was applied at the last index. |

The patterns are NOT returned in `RepoStatus` (the lightweight job-status response); they live on the repo entity itself.

---

## Entity 4 — Stream frames (in-memory typed dicts)

Real-time messages on the WebSocket channel `WS /api/jobs/{job_id}/stream`. Not persisted.

**Location**: `backend/src/codesensei/jobs_stream/schema.py`

### `InitFrame`

| Field | Type | Notes |
|-------|------|-------|
| `kind` | `Literal["init"]` | Discriminator. |
| `state` | `Literal["queued", "running", "success", "failed", "cancelled"]` | Current job state at subscribe time. |
| `files_total` | `int \| None` | Known after the file-walk phase; `None` while still discovering. |
| `files_done` | `int` | Files whose chunks have been embedded + stored. |
| `chunks_done` | `int` | Total chunks committed so far. |
| `started_at` | `string (ISO-8601)` | Worker `started_at` timestamp. |
| `eta_seconds` | `int \| None` | Best-effort estimate (`files_total - files_done` × moving average); `None` if `files_total` unknown. |

### `ProgressFrame`

| Field | Type | Notes |
|-------|------|-------|
| `kind` | `Literal["progress"]` | |
| `files_done` | `int` | |
| `files_total` | `int \| None` | |
| `chunks_done` | `int` | |
| `current_file` | `string \| None` | Relative-to-repo-root path of the file currently being chunked. `None` between files. |

### `CompleteFrame`

| Field | Type | Notes |
|-------|------|-------|
| `kind` | `Literal["complete"]` | |
| `state` | `Literal["success", "failed", "cancelled"]` | Terminal state. |
| `error_category` | `string \| None` | Existing index-error category enum (`payload_too_large`, `unreachable_source`, `embedding_provider_error`, etc.). `None` on success. |
| `error_message` | `string \| None` | Human-readable summary. `None` on success. |
| `final_files` | `int` | Final `files_done` value. |
| `final_chunks` | `int` | Final `chunks_done` value. |

**Validation**: TypedDicts (NOT pydantic models) for speed; the channel is high-frequency and there is no need for runtime coercion (publisher controls the shape). The WS handler does `ws.send_text(json_string)` directly with the raw publisher output.

**Channel naming**: `codesensei:job:<job_id>` (one channel per job UUID). No globbing.

---

## State transitions

### `IgnoreSpec`

Stateless dataclass — no transitions.

### `repos.codesensei_ignore_patterns`

```
NULL  →  list[str]   on a successful index run with ≥ 1 pattern
NULL  →  NULL        on a successful index run with no .codesensei-ignore (or empty file)
list[str]  →  NULL   on a successful index run that no longer finds the file
list[str]  →  list[str]   on a successful index run that finds a new pattern list
```

Failed index runs leave the column UNCHANGED (the row is rolled back inside the same session).

### Stream channel

```
client subscribe   →  init frame   →  N × progress frames   →  complete frame   →  ws.close(1000)
client subscribe   →  4404 close (unknown job_id)
client subscribe   →  init(state="success"|"failed")   →  complete frame   →  ws.close(1000)  (job already terminal)
```

No mid-stream replay or buffering. Disconnect mid-stream → SPA falls back to polling per FR-012.
