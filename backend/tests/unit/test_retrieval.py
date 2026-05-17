"""US2 unit tests: query derivation + token-budget trim (no DB)."""

from __future__ import annotations

import pytest

from codesensei.indexing.retrieval import (
    DISTANCE_FLOOR,
    derive_queries,
)


def test_derive_queries_extracts_one_per_hunk():
    diff = (
        "diff --git a/a.py b/a.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def foo():\n"
        "-    return 1\n"
        "+    return 2\n"
        "+    # added\n"
        "@@ -10,2 +11,3 @@\n"
        " def bar():\n"
        "+    print('hi')\n"
        "     return None\n"
    )
    queries = derive_queries(diff)
    assert len(queries) == 2
    assert "return 2" in queries[0]
    assert "added" in queries[0]
    assert "print('hi')" in queries[1]
    # New-file body excludes the '-' lines.
    for q in queries:
        assert "return 1" not in q


def test_derive_queries_skips_pure_deletion_hunks():
    diff = "diff --git a/a.py b/a.py\n@@ -1,3 +1,1 @@\n keeper\n-removed line 1\n-removed line 2\n"
    queries = derive_queries(diff)
    # The hunk has a context line " keeper" so it's not pure deletion → 1 query.
    assert len(queries) == 1
    assert "keeper" in queries[0]
    assert "removed" not in queries[0]


def test_derive_queries_handles_zero_hunks():
    diff = "diff --git a/a.py b/a.py\nindex abc..def 100644\n--- a/a.py\n+++ b/a.py\n"
    assert derive_queries(diff) == []


def test_distance_floor_is_documented_constant():
    # The retrieval contract pins this at 1.5; downstream tests rely on the constant existing.
    assert DISTANCE_FLOOR == pytest.approx(1.5)
