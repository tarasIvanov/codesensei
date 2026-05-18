"""Unit tests for the temporal-hints injection in ``review.prompt`` — feature 008."""

from __future__ import annotations

from codesensei.review.git_temporal import LineWindow, TemporalEntry
from codesensei.review.prompt import render_user_message

_DIFF = """diff --git a/src/x.py b/src/x.py
index 1..2 100644
--- a/src/x.py
+++ b/src/x.py
@@ -1,1 +1,1 @@
-old
+new
"""


def _entry(short: str, date: str, email: str, subject: str) -> TemporalEntry:
    return TemporalEntry(
        commit_sha=short + "0" * (40 - len(short)),
        short_sha=short[:7].ljust(7, "0"),
        author_email=email,
        author_date=date,
        subject=subject,
        hunk_lines_changed=1,
    )


def test_non_empty_pool_emits_block_with_correct_format() -> None:
    pool = {
        "src/x.py": [
            (
                LineWindow(40, 60),
                [
                    _entry("abc1234", "2026-01-15T10:42:13+00:00", "alice@example.org", "Fix race"),
                    _entry("def5678", "2025-11-02T18:01:55+00:00", "bob@example.org", "Add guard"),
                ],
            )
        ]
    }
    out = render_user_message(diff=_DIFF, temporal_pool=pool)
    assert "Code history hints" in out
    assert "File: src/x.py (lines 40-60)" in out
    assert "abc1234" in out and "2026-01-15" in out and "alice@example.org" in out
    assert "def5678" in out and "2025-11-02" in out and "bob@example.org" in out
    # Header appears BEFORE the diff body.
    assert out.index("Code history hints") < out.index("Review the following unified diff")


def test_empty_pool_omits_header() -> None:
    out = render_user_message(diff=_DIFF, temporal_pool={})
    assert "Code history hints" not in out


def test_pool_with_only_empty_entries_omits_header() -> None:
    pool = {"src/x.py": [(LineWindow(1, 10), [])]}
    out = render_user_message(diff=_DIFF, temporal_pool=pool)
    assert "Code history hints" not in out


def test_none_pool_byte_identical_to_pre_feature() -> None:
    """With no chunks and no pool, the prompt body matches the pre-008 shape."""
    pre = render_user_message(diff=_DIFF)
    post = render_user_message(diff=_DIFF, temporal_pool=None)
    assert pre == post
    # Also assert the pre-008 literal body.
    assert pre == f"Review the following unified diff:\n\n```diff\n{_DIFF}\n```"
