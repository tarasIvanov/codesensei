"""Per-line-window git-log temporal context for findings (feature 008)."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID
from weakref import WeakValueDictionary

import structlog

if TYPE_CHECKING:
    pass

# Module-private constants (FR-018: no env exposure in v1).
_CACHE_ROOT = Path("/var/tmp/codesensei-temporal")
_MAX_CACHED_REPOS = 5
_CALL_TIMEOUT_S = 1.5
_TOTAL_BUDGET_S = 2.0
_STALE_CLONE_S = 3600
_MAX_LINE_RANGE = 200
_MAX_WINDOWS_PER_FILE = 3
_MAX_ENTRIES_PER_WINDOW = 5
_PRETTY_FORMAT = "%H%x09%h%x09%ae%x09%aI%x09%s"
_SUBJECT_MAX = 120

_logger = structlog.get_logger(__name__)

# Test seam: when set, `_clone_or_reuse` short-circuits and returns the result.
# Production code MUST leave this as None.
_clone_for_test: Callable[[str], Path | None] | None = None

# Per-cache-key lock to guard the clone/fetch transition. Read paths (`git log`)
# are concurrency-safe and do NOT take the lock.
_clone_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


class _TemporalSubprocessError(Exception):
    """Raised internally when a git subprocess exits non-zero or times out."""


# ---------------------------------------------------------------------------
# Data shapes (module-private dataclasses; the wire-shape pydantic equivalent
# lives in review/schema.py).
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class TemporalEntry:
    commit_sha: str
    short_sha: str
    author_email: str
    author_date: str
    subject: str
    hunk_lines_changed: int


@dataclass(slots=True, frozen=True)
class LineWindow:
    start_line: int
    end_line: int


# Pool returned by `fetch_temporal_pool_for_review`.
FileTemporalPool = dict[str, list[tuple[LineWindow, list[TemporalEntry]]]]


@dataclass(slots=True)
class TemporalCollectionSummary:
    repo_id: UUID | None = None
    files_count: int = 0
    entries_total: int = 0
    elapsed_ms: int = 0
    budget_exceeded: bool = False
    files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Clone-cache primitives.
# ---------------------------------------------------------------------------


def _cache_key(repo_source: str) -> str:
    return hashlib.sha1(repo_source.encode("utf-8")).hexdigest()


def _evict_if_needed() -> None:
    if not _CACHE_ROOT.exists():
        return
    entries = [p for p in _CACHE_ROOT.iterdir() if p.is_dir()]
    if len(entries) <= _MAX_CACHED_REPOS:
        return
    entries.sort(key=lambda p: p.stat().st_mtime)
    while len(entries) > _MAX_CACHED_REPOS:
        oldest = entries.pop(0)
        shutil.rmtree(oldest, ignore_errors=True)


async def _run_git(
    *args: str,
    cwd: Path | None = None,
    timeout: float = _CALL_TIMEOUT_S,  # noqa: ASYNC109 — per-call hard cap applied via asyncio.wait_for below
) -> str:
    env = {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/true",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:  # noqa: BLE001
            pass
        raise
    if proc.returncode != 0:
        first_line = stderr.decode("utf-8", errors="replace").splitlines()[0:1]
        reason = first_line[0] if first_line else f"exit {proc.returncode}"
        raise _TemporalSubprocessError(reason)
    return stdout.decode("utf-8", errors="replace")


async def _clone(repo_source: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # `--filter=blob:none --no-checkout` keeps commits + trees but skips blobs
    # and working-tree materialisation (R2 in research.md).
    await _run_git(
        "clone",
        "--filter=blob:none",
        "--no-checkout",
        "--quiet",
        repo_source,
        str(dest),
        timeout=_CALL_TIMEOUT_S * 4,  # clone is the one heavy op; allow 6 s budget
    )


async def _fetch(cache_dir: Path) -> None:
    await _run_git(
        "-C",
        str(cache_dir),
        "fetch",
        "--all",
        "--prune",
        "--quiet",
        timeout=_CALL_TIMEOUT_S * 2,
    )


def _is_https_source(repo_source: str) -> bool:
    return repo_source.startswith("https://") or repo_source.startswith("http://")


async def _clone_or_reuse(repo_source: str) -> Path | None:
    """Return a path to a usable bare-ish clone, or None for unsupported sources."""
    if _clone_for_test is not None:
        return _clone_for_test(repo_source)
    if not _is_https_source(repo_source):
        return None

    digest = _cache_key(repo_source)
    cache_dir = _CACHE_ROOT / digest
    lock = _clone_locks.setdefault(digest, asyncio.Lock())
    async with lock:
        if not cache_dir.exists():
            try:
                await _clone(repo_source, cache_dir)
            except (TimeoutError, _TemporalSubprocessError, OSError) as exc:
                _logger.warning(
                    "temporal_fetch_failed",
                    repo_source=repo_source,
                    file_path="<clone>",
                    reason=str(exc)[:200],
                )
                # Clean up half-cloned dir.
                shutil.rmtree(cache_dir, ignore_errors=True)
                return None
            _evict_if_needed()
        else:
            try:
                age = time.time() - cache_dir.stat().st_mtime
            except OSError:
                age = 0.0
            if age > _STALE_CLONE_S:
                try:
                    await _fetch(cache_dir)
                except (TimeoutError, _TemporalSubprocessError, OSError) as exc:
                    _logger.warning(
                        "temporal_fetch_failed",
                        repo_source=repo_source,
                        file_path="<fetch>",
                        reason=str(exc)[:200],
                    )
                    # Fall through and use the stale clone anyway.
        try:
            os.utime(cache_dir, None)
        except OSError:
            pass
        return cache_dir


# ---------------------------------------------------------------------------
# Diff-hunk → line-window collapsing.
# ---------------------------------------------------------------------------


def collapse_diff_to_windows(
    rhs_hunks_by_file: Mapping[str, Sequence[tuple[int, int]]],
) -> dict[str, list[LineWindow]]:
    """Collapse PR-diff RHS hunks into ≤ 3 windows per file (each ≤ 200 lines)."""
    out: dict[str, list[LineWindow]] = {}
    for path, raw_hunks in rhs_hunks_by_file.items():
        # Normalise to (start, end) and drop empty.
        ranges: list[tuple[int, int]] = []
        for start, length in raw_hunks:
            if length <= 0:
                continue
            ranges.append((start, start + length - 1))
        if not ranges:
            continue
        ranges.sort()
        merged: list[list[int]] = []
        for s, e in ranges:
            if merged and s - merged[-1][1] <= 5:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        windows: list[LineWindow] = []
        for s, e in merged:
            if e - s + 1 > _MAX_LINE_RANGE:
                e = s + _MAX_LINE_RANGE - 1
            windows.append(LineWindow(start_line=s, end_line=e))
        out[path] = windows[:_MAX_WINDOWS_PER_FILE]
    return out


# ---------------------------------------------------------------------------
# Per-call fetch.
# ---------------------------------------------------------------------------


def _parse_log_records(stdout: str) -> list[TemporalEntry]:
    entries: list[TemporalEntry] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        sha, short, email, date, subject = parts
        if len(sha) != 40 or len(short) != 7:
            continue
        if len(subject) > _SUBJECT_MAX:
            subject = subject[: _SUBJECT_MAX - 1] + "…"
        entries.append(
            TemporalEntry(
                commit_sha=sha,
                short_sha=short,
                author_email=email,
                author_date=date,
                subject=subject,
                hunk_lines_changed=0,
            )
        )
    return entries


def _count_hunk_lines(patch: str) -> dict[str, int]:
    """Map full-sha → count of +/- lines in its patch body (best effort)."""
    counts: dict[str, int] = {}
    current_sha: str | None = None
    current = 0
    for raw in patch.splitlines():
        if not raw:
            continue
        if len(raw) == 40 and all(c in "0123456789abcdef" for c in raw):
            if current_sha is not None:
                counts[current_sha] = current
            current_sha = raw
            current = 0
            continue
        if raw.startswith(("@@", "diff ", "---", "+++")):
            continue
        if raw.startswith("+") or raw.startswith("-"):
            current += 1
    if current_sha is not None:
        counts.setdefault(current_sha, current)
    return counts


async def fetch_temporal_context(
    repo_source: str,
    file_path: str,
    window: LineWindow,
    *,
    max_commits: int = _MAX_ENTRIES_PER_WINDOW,
) -> list[TemporalEntry]:
    """Return the most-recent commits that touched `file_path` lines in `window`."""
    # Clamp window range (FR-006).
    start, end = window.start_line, window.end_line
    if end - start + 1 > _MAX_LINE_RANGE:
        end = start + _MAX_LINE_RANGE - 1
    if start < 1 or end < start:
        return []

    try:
        cache_dir = await _clone_or_reuse(repo_source)
    except Exception as exc:  # noqa: BLE001 — defensive belt-and-braces
        _logger.warning(
            "temporal_fetch_failed",
            repo_source=repo_source,
            file_path=file_path,
            reason=f"clone_or_reuse:{exc!s}"[:200],
        )
        return []
    if cache_dir is None:
        return []

    range_arg = f"{start},{end}:{file_path}"
    try:
        stdout = await _run_git(
            "-C",
            str(cache_dir),
            "log",
            "-L",
            range_arg,
            "-n",
            str(max_commits),
            f"--pretty=format:{_PRETTY_FORMAT}",
            "--no-patch",
            "--no-color",
            timeout=_CALL_TIMEOUT_S,
        )
    except (TimeoutError, _TemporalSubprocessError, OSError, UnicodeDecodeError) as exc:
        _logger.warning(
            "temporal_fetch_failed",
            repo_source=repo_source,
            file_path=file_path,
            reason=str(exc)[:200],
        )
        return []

    entries = _parse_log_records(stdout)
    if not entries:
        return []

    # Best-effort hunk-line counting on the first ≤ 8 commits.
    try:
        patch_stdout = await _run_git(
            "-C",
            str(cache_dir),
            "log",
            "-L",
            range_arg,
            "-n",
            "8",
            "--pretty=format:%H",
            "--unified=0",
            "--no-color",
            timeout=_CALL_TIMEOUT_S,
        )
        counts = _count_hunk_lines(patch_stdout)
        entries = [
            TemporalEntry(
                commit_sha=e.commit_sha,
                short_sha=e.short_sha,
                author_email=e.author_email,
                author_date=e.author_date,
                subject=e.subject,
                hunk_lines_changed=counts.get(e.commit_sha, 0),
            )
            for e in entries
        ]
    except (TimeoutError, _TemporalSubprocessError, OSError, UnicodeDecodeError):
        # Leave hunk_lines_changed at 0 silently — primary data already collected.
        pass

    return entries


# ---------------------------------------------------------------------------
# Per-review pool collection.
# ---------------------------------------------------------------------------


async def fetch_temporal_pool_for_review(
    *,
    repo_id: UUID | None,
    repo_source: str,
    windows_by_file: Mapping[str, Sequence[LineWindow]],
) -> tuple[FileTemporalPool, TemporalCollectionSummary]:
    """Fan out per-file lookups under a 2.0 s soft total budget."""
    summary = TemporalCollectionSummary(repo_id=repo_id)
    pool: FileTemporalPool = {}
    if not windows_by_file:
        summary.elapsed_ms = 0
        return pool, summary

    t0 = time.perf_counter()

    async def _fetch_one(
        path: str, window: LineWindow
    ) -> tuple[str, LineWindow, list[TemporalEntry]]:
        entries = await fetch_temporal_context(repo_source, path, window)
        return path, window, entries

    tasks: list[asyncio.Task[tuple[str, LineWindow, list[TemporalEntry]]]] = []
    try:
        async with asyncio.TaskGroup() as tg:
            for path, windows in windows_by_file.items():
                for window in windows:
                    elapsed = time.perf_counter() - t0
                    if elapsed > _TOTAL_BUDGET_S:
                        summary.budget_exceeded = True
                        break
                    tasks.append(tg.create_task(_fetch_one(path, window)))
                if summary.budget_exceeded:
                    break
    except* Exception as eg:  # noqa: BLE001
        # TaskGroup wraps child exceptions; per-call fetch never raises by
        # contract, so this only fires on programmer error — log loudly.
        for exc in eg.exceptions:
            _logger.warning(
                "temporal_fetch_failed",
                repo_source=repo_source,
                file_path="<taskgroup>",
                reason=str(exc)[:200],
            )

    seen_files: set[str] = set()
    for task in tasks:
        if task.cancelled() or task.exception() is not None:
            continue
        path, window, entries = task.result()
        if not entries:
            continue
        pool.setdefault(path, []).append((window, entries))
        seen_files.add(path)
        summary.entries_total += len(entries)

    # Final wall-clock budget exceeded?
    summary.elapsed_ms = int((time.perf_counter() - t0) * 1000)
    if (time.perf_counter() - t0) > _TOTAL_BUDGET_S:
        summary.budget_exceeded = True
    summary.files_count = len(pool)
    summary.files = sorted(seen_files)
    return pool, summary


__all__ = [
    "TemporalEntry",
    "LineWindow",
    "FileTemporalPool",
    "TemporalCollectionSummary",
    "collapse_diff_to_windows",
    "fetch_temporal_context",
    "fetch_temporal_pool_for_review",
]


def __getattr__(name: str) -> object:  # pragma: no cover — module-attr glue for tests
    if name == "_clone_for_test":
        return _clone_for_test
    raise AttributeError(name)
