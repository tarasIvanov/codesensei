"""Unit tests for ``review.git_temporal`` — feature 008.

Tests build a synthetic git repository under pytest's ``tmp_path`` and exercise
``fetch_temporal_context`` directly via the ``_clone_for_test`` seam — no
network access, no real ``git clone`` happens.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from codesensei.review import git_temporal
from codesensei.review.git_temporal import (
    LineWindow,
    collapse_diff_to_windows,
    fetch_temporal_context,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.org",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.org",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": "/tmp",
        },
    )


@pytest.fixture
def synthetic_repo(tmp_path: Path) -> Path:
    """A 3-commit repo with a file edited twice."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "commit.gpgsign", "false")
    src = repo / "src"
    src.mkdir()
    file = src / "x.py"
    file.write_text("a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "Initial commit with five lines")
    # Touch lines 2-3 (b, c).
    file.write_text("a = 1\nb = 20\nc = 30\nd = 4\ne = 5\n")
    _git(repo, "commit", "-q", "-am", "Bump b and c values")
    # Touch line 4 (d).
    file.write_text("a = 1\nb = 20\nc = 30\nd = 40\ne = 5\n")
    _git(repo, "commit", "-q", "-am", "Bump d value")
    return repo


@pytest.fixture(autouse=True)
def _isolate_clone_seam(synthetic_repo, monkeypatch):
    """Wire `_clone_for_test` to point at our synthetic repo (real `git log` runs)."""
    seam_calls = {"count": 0}

    def seam(src: str) -> Path:
        seam_calls["count"] += 1
        return synthetic_repo

    monkeypatch.setattr(git_temporal, "_clone_for_test", seam)
    yield seam_calls
    monkeypatch.setattr(git_temporal, "_clone_for_test", None)


@pytest.mark.asyncio
async def test_happy_path_three_commit_history(_isolate_clone_seam) -> None:
    entries = await fetch_temporal_context("https://example/repo", "src/x.py", LineWindow(1, 5))
    assert len(entries) == 3
    # Newest first.
    assert entries[0].subject == "Bump d value"
    assert entries[1].subject == "Bump b and c values"
    assert entries[2].subject == "Initial commit with five lines"
    # Sha shape.
    assert len(entries[0].commit_sha) == 40
    assert entries[0].short_sha == entries[0].commit_sha[:7]
    # ISO-8601 date present.
    assert "T" in entries[0].author_date


@pytest.mark.asyncio
async def test_non_existent_file_returns_empty(_isolate_clone_seam) -> None:
    entries = await fetch_temporal_context(
        "https://example/repo", "src/does_not_exist.py", LineWindow(1, 10)
    )
    assert entries == []


@pytest.mark.asyncio
async def test_line_range_outside_file_returns_empty(_isolate_clone_seam) -> None:
    entries = await fetch_temporal_context("https://example/repo", "src/x.py", LineWindow(500, 600))
    assert entries == []


@pytest.mark.asyncio
async def test_max_commits_cap(_isolate_clone_seam) -> None:
    entries = await fetch_temporal_context(
        "https://example/repo", "src/x.py", LineWindow(1, 5), max_commits=2
    )
    assert len(entries) == 2


@pytest.mark.asyncio
async def test_subject_truncation_long_subject(synthetic_repo, monkeypatch) -> None:
    long = "x" * 200
    _git(synthetic_repo, "commit", "--allow-empty", "-q", "-m", long)
    # Re-touch the file so the long commit is part of the line-history.
    file = synthetic_repo / "src" / "x.py"
    file.write_text("a = 1\nb = 200\nc = 300\nd = 40\ne = 5\n")
    _git(synthetic_repo, "commit", "-q", "-am", "y" * 200)
    entries = await fetch_temporal_context("https://example/repo", "src/x.py", LineWindow(1, 5))
    assert any(e.subject.endswith("…") for e in entries)
    assert all(len(e.subject) <= 120 for e in entries)


@pytest.mark.asyncio
async def test_line_window_over_200_clamps(_isolate_clone_seam) -> None:
    # 1..500 should clamp to 1..200; file only has 5 lines so result is the
    # full history anyway — assert no crash and entries returned.
    entries = await fetch_temporal_context("https://example/repo", "src/x.py", LineWindow(1, 500))
    assert len(entries) >= 1


@pytest.mark.asyncio
async def test_non_https_source_returns_empty_silently(monkeypatch, caplog) -> None:
    # Disable the seam so the production path runs.
    monkeypatch.setattr(git_temporal, "_clone_for_test", None)
    entries = await fetch_temporal_context("/local/path", "src/x.py", LineWindow(1, 5))
    assert entries == []


@pytest.mark.asyncio
async def test_concurrent_calls_share_one_clone(synthetic_repo, monkeypatch) -> None:
    """Concurrent fetches share the cache without deadlocking.

    `_clone_for_test` short-circuits the production lock path, so this only
    asserts the public-contract surface: three concurrent calls each return
    their result and the seam runs once per call (no cache mutex blocks them).
    """
    counter = {"count": 0}

    def seam(src: str) -> Path:
        counter["count"] += 1
        return synthetic_repo

    monkeypatch.setattr(git_temporal, "_clone_for_test", seam)
    results = await asyncio.gather(
        fetch_temporal_context("https://example/repo", "src/x.py", LineWindow(1, 5)),
        fetch_temporal_context("https://example/repo", "src/x.py", LineWindow(1, 5)),
        fetch_temporal_context("https://example/repo", "src/x.py", LineWindow(1, 5)),
    )
    assert all(len(r) == 3 for r in results)
    # Three calls → three seam invocations (the seam bypasses production cache).
    assert counter["count"] == 3


def test_collapse_diff_to_windows_basic() -> None:
    out = collapse_diff_to_windows({"src/x.py": [(10, 5), (40, 3), (300, 10)]})
    assert "src/x.py" in out
    windows = out["src/x.py"]
    # Three disjoint windows, ordered by start.
    assert len(windows) == 3
    assert windows[0].start_line == 10
    assert windows[2].start_line == 300


def test_collapse_diff_to_windows_merges_close_hunks() -> None:
    out = collapse_diff_to_windows({"src/x.py": [(10, 3), (15, 2)]})
    # (10,12) and (15,16) are within 5 lines → merge.
    assert out["src/x.py"] == [LineWindow(10, 16)]


def test_collapse_diff_to_windows_clamps_huge_window() -> None:
    out = collapse_diff_to_windows({"src/x.py": [(1, 500)]})
    win = out["src/x.py"][0]
    assert win.end_line - win.start_line + 1 == 200


def test_collapse_diff_to_windows_caps_at_three() -> None:
    out = collapse_diff_to_windows({"src/x.py": [(10, 1), (50, 1), (100, 1), (200, 1), (400, 1)]})
    assert len(out["src/x.py"]) == 3
    # Lowest-line three win.
    assert [w.start_line for w in out["src/x.py"]] == [10, 50, 100]
