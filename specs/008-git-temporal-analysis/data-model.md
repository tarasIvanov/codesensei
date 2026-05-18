# Data Model — 008 Git Temporal Analysis

All entities here are **transient**: in-memory at request time, or on-disk inside the API container's runtime cache. No DB row is added, no alembic migration is generated.

## Wire entity

### `TemporalEntry` (Pydantic, `review/schema.py`)

| Field | Type | Constraints | Source |
|-------|------|-------------|--------|
| `commit_sha` | `str` | 40-char lowercase hex | `git log %H` |
| `short_sha` | `str` | 7-char lowercase hex (matches `commit_sha[:7]`) | `git log %h` |
| `author_email` | `str` | non-empty, ≤ 254 chars; not validated as an RFC-5321 address (some git histories carry placeholder noreply addresses) | `git log %ae` |
| `author_date` | `str` | ISO-8601 ("YYYY-MM-DDTHH:MM:SS±HH:MM") | `git log %aI` |
| `subject` | `str` | non-empty, truncated server-side to ≤ 120 chars with single trailing `…` if longer | `git log %s` |
| `hunk_lines_changed` | `int` | ≥ 0; sum of `+` and `-` lines inside the window from the first patch found via the `--unified=0` follow-up pass; defaults to 0 if the patch parse failed | parsed from `git log -L --unified=0` |

Pydantic v2 config: `model_config = ConfigDict(extra="ignore")`. The model is part of the SDK-style wire surface — extra unknown fields from the model are silently dropped, which lets us evolve the shape additively later.

### `Finding` (existing, modified)

Existing fields untouched. One new optional field is appended:

| Field | Type | Constraints |
|-------|------|-------------|
| `temporal_context` | `list[TemporalEntry] \| None` | `None` (omitted) when no entries match the finding's `(file, line)`; non-empty list otherwise. The empty list `[]` is normalised to `None` server-side so the wire stays minimal. |

## In-memory (request-scoped) entities

### `LineWindow`

A range derived from the PR diff for a single file. Internal to `review/git_temporal.py` and `review/service.py`; not on the wire.

```python
@dataclass(slots=True, frozen=True)
class LineWindow:
    start_line: int   # inclusive, RHS line number, ≥ 1
    end_line: int     # inclusive, ≥ start_line
```

Invariants enforced at construction:
- `end_line - start_line + 1 ≤ 200` (FR-006). Larger ranges are clamped to `(start, start + 199)`.
- For a single file, windows produced by the collapser are pairwise disjoint and ordered by `start_line` ascending.
- At most 3 windows per file (the lowest-line 3 win on tie; rest are dropped to fit budget).

### `FileTemporalPool`

The shape returned by `fetch_temporal_pool_for_review`:

```python
FileTemporalPool = dict[str, list[tuple[LineWindow, list[TemporalEntry]]]]
```

- Outer key: file path (RHS of the diff, e.g. `src/auth/middleware.py`).
- Inner list: at most 3 `(window, entries)` pairs per file.
- `entries` length is `0 ≤ n ≤ 5` (per FR-002, cap of 5 most-recent commits per window).
- When an outer-key would map to a list whose all `entries` are empty, the outer key is *omitted entirely* — `pool.get(file)` returns `None` for such files. This keeps the downstream "is the prompt block worth emitting" check trivial.

### `TemporalCollectionSummary`

Internal counter object passed to the single `_logger.info("temporal_fetch", ...)` call (FR-020).

```python
@dataclass(slots=True)
class TemporalCollectionSummary:
    repo_id: UUID
    files_count: int            # number of (file, windows) pairs attempted
    entries_total: int          # sum of len(entries) over all (window, entries) tuples
    elapsed_ms: int             # wall-clock since the outer call began
    budget_exceeded: bool       # True iff total elapsed crossed 2.0 s mid-collection
```

## Filesystem entity (container-internal)

### `CachedClone`

Logical record represented by a single directory under the cache root. Not in the DB, not on the wire.

| Property | Value |
|----------|-------|
| Path | `/var/tmp/codesensei-temporal/<sha1(source)>/` |
| Created by | `git clone --filter=blob:none --no-checkout <source> <path>` |
| Refreshed by | `git fetch --all --prune --quiet` when `time.time() - os.stat(path).st_mtime > 3600` |
| Touched (LRU bump) by | `os.utime(path, None)` after each successful lookup against it |
| Evicted by | `shutil.rmtree(oldest_by_mtime)` when the cache-root directory count > 5 |
| Owner | The API process (rwx for the container user; not exposed via volume or HTTP) |

State machine:
- **Missing** → on lookup → **Materialising** (`git clone` running) → **Ready** (touch mtime, lookup proceeds).
- **Ready** + age > 1 h → on next lookup → **Refreshing** (`git fetch` running) → **Ready** (touch mtime).
- **Ready** + cache-count > 5 + oldest → **Evicted** (rmtree).
- **Ready** + clone process dies / disk full → **Failed** (entry remains as-is; next lookup retries clone after a `rmtree`).

Race control: a module-level `WeakValueDictionary[str, asyncio.Lock]` is consulted before transitions; each cache key has its own lock, acquired around the clone/fetch step but **not** around the per-call `git log -L` (the read path is concurrency-safe).

## What is NOT in the data model

- No new SQLAlchemy model, no new alembic revision, no new table.
- No new pydantic Settings field, no `.env.example` entry.
- No new compose service, no new host-mounted volume.
- No persistence of `TemporalEntry` across reviews — the only persistence is the cached clone, and that's a *compute* artefact, not a domain entity.
- No client-side normalisation of the wire shape — the SPA reads `temporal_context` exactly as the backend serialises it (snake_case).
