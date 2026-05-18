# Contract: `review/git_temporal.py`

Module-level contract for the new backend module. Documents the public surface, runtime-cache invariants, and the test seam.

## Module-level constants (private)

```python
_CACHE_ROOT       = Path("/var/tmp/codesensei-temporal")
_MAX_CACHED_REPOS = 5
_CALL_TIMEOUT_S   = 1.5
_TOTAL_BUDGET_S   = 2.0
_STALE_CLONE_S    = 3600
_MAX_LINE_RANGE   = 200
_MAX_WINDOWS_PER_FILE = 3
_MAX_ENTRIES_PER_WINDOW = 5
_PRETTY_FORMAT    = "%H%x09%h%x09%ae%x09%aI%x09%s"
```

These are intentionally private (leading `_`). FR-018 (no env exposure in v1) anchors that promise.

## Public symbols

### `dataclass TemporalEntry`

```python
@dataclass(slots=True, frozen=True)
class TemporalEntry:
    commit_sha: str
    short_sha: str
    author_email: str
    author_date: str
    subject: str
    hunk_lines_changed: int
```

Identical field set to the pydantic wire model in `review/schema.py`. Module returns the dataclass form; `service.py` converts to the pydantic form when populating `Finding.temporal_context`.

### `dataclass LineWindow`

```python
@dataclass(slots=True, frozen=True)
class LineWindow:
    start_line: int
    end_line: int
```

### `async def fetch_temporal_context(...)`

```python
async def fetch_temporal_context(
    repo_source: str,
    file_path: str,
    window: LineWindow,
    *,
    max_commits: int = _MAX_ENTRIES_PER_WINDOW,
) -> list[TemporalEntry]:
```

Behaviour:
- Resolves `repo_source` → cache directory; clones / fetches as needed under the per-key lock.
- Runs `git -C <cache_dir> log -L <s>,<e>:<file> -n <max_commits> --pretty=format:<PRETTY> --no-patch --no-color` via `asyncio.create_subprocess_exec`.
- Wraps the call in `asyncio.wait_for(..., timeout=_CALL_TIMEOUT_S)`.
- Parses the stdout (TAB-separated, one record per non-empty line).
- For the first ≤ 8 returned commit SHAs, runs a follow-up `git log -L <s>,<e>:<file> -n 8 --unified=0 --no-color --pretty=format:%H` to count hunk lines per commit (cheap because both commits and trees are local after clone).
- On *any* failure (`OSError`, `asyncio.TimeoutError`, subprocess non-zero exit, parse error, file not in history, range outside file), returns `[]` and emits a single `_logger.warning("temporal_fetch_failed", repo_source=…, file_path=…, reason=…)` event. Never raises.
- Repository sources whose canonical form is not an `https://` URL return `[]` silently with no log entry (FR-021).

### `async def fetch_temporal_pool_for_review(...)`

```python
async def fetch_temporal_pool_for_review(
    *,
    repo_id: UUID,
    repo_source: str,
    windows_by_file: Mapping[str, Sequence[LineWindow]],
) -> tuple[FileTemporalPool, TemporalCollectionSummary]:
```

Behaviour:
- Iterates the input map, fanning out per-file lookups via `asyncio.TaskGroup`.
- Tracks elapsed wall-clock; cancels still-pending sub-tasks when `elapsed > _TOTAL_BUDGET_S` (sets `summary.budget_exceeded = True`).
- Returns a `FileTemporalPool` (dict of file → list of (window, entries)). Files with all-empty entries are dropped.
- The returned `TemporalCollectionSummary` is the structured-logging payload for FR-020 — the caller is expected to log it once.

### `def collapse_diff_to_windows(...)`

```python
def collapse_diff_to_windows(
    rhs_hunks_by_file: Mapping[str, Sequence[tuple[int, int]]],
) -> dict[str, list[LineWindow]]:
```

Behaviour:
- Input: per-file list of RHS hunk ranges `(start, length)` from `review/github_diff.py:parse_hunks()`.
- Output: per-file list of ≤ 3 `LineWindow`s; pairwise disjoint, ordered by `start_line` asc, each ≤ 200 lines.
- Collapse rule: two hunks whose end-points are within 5 lines of each other merge into one window. After collapsing, if the file has > 3 windows, drop the highest-line ones until ≤ 3 remain.

### Test seam: `_clone_for_test`

The module exposes a module-private callable `_clone_for_test: Callable[[str], Path] | None = None` (module attribute, default `None`). When non-`None`, `_clone_or_reuse(repo_source)` short-circuits and returns `_clone_for_test(repo_source)` instead of running `git clone`. Unit tests `monkeypatch.setattr` it onto the module to point at a pytest-`tmp_path`-managed git repo, sidestepping real network clones.

## Cache invariants

These are testable in unit tests and stated as invariants:

1. **Single in-flight clone per key** — concurrent calls for the same `repo_source` see exactly one `git clone` subprocess; the second caller awaits the lock and reuses the resulting directory.
2. **Eviction bounded at 5** — after N (N ≤ 10) calls against N distinct sources, the cache root contains exactly `min(N, 5)` subdirectories; the survivors are the 5 most-recently-touched.
3. **Refresh bounded at 1 h** — successive calls against the same source within 1 h skip `git fetch`; calls after 1 h run `git fetch` exactly once (the second call within the next hour does not run it again because the touch resets mtime).
4. **No exception escapes** — every failure mode (`OSError`, `asyncio.TimeoutError`, non-zero exit, parse error, file-not-in-history, range-clamp, non-HTTPS source) returns an empty list and never raises to the caller.
5. **No blocking syscall on the request task** — `git clone`, `git fetch`, `git log`, and the `os.utime` LRU bump all run under `asyncio.create_subprocess_exec` or are O(1) metadata operations.

## Structured-logging contract

Two and only two event names are emitted from this module:

- `_logger.warning("temporal_fetch_failed", repo_source: str, file_path: str, reason: str)` — one per *failed* individual lookup (FR-019).
- `_logger.info("temporal_fetch", repo_id: UUID, files_count: int, entries_total: int, elapsed_ms: int, budget_exceeded: bool)` — emitted **by the caller** (`review/service.py`) using the returned `TemporalCollectionSummary`, exactly once per review against an indexed repo (FR-020).

No `print()`. No raw `logging.error(...)`. No multi-line log payloads.
