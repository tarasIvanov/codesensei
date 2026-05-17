"""US2 unit tests: USER prompt with RAG context block."""

from __future__ import annotations

from dataclasses import dataclass

from codesensei.review.prompt import (
    SYSTEM_MESSAGE,
    USER_TEMPLATE,
    build_messages,
    render_user_message,
)


@dataclass(frozen=True)
class FakeChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    token_count: int


def test_user_message_byte_equivalent_when_no_chunks():
    diff = "diff --git a/x.py b/x.py\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    out = render_user_message(diff=diff, retrieved_chunks=None)
    assert out == USER_TEMPLATE.format(DIFF=diff)
    # Also when explicitly empty.
    out2 = render_user_message(diff=diff, retrieved_chunks=[])
    assert out2 == USER_TEMPLATE.format(DIFF=diff)


def test_user_message_with_chunks_contains_context_block_first():
    diff = "diff --git a/x.py b/x.py\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    chunks = [
        FakeChunk(
            "billing.py",
            10,
            24,
            "def compute_total(items):\n    return sum(i.price for i in items)",
            42,
        ),
        FakeChunk(
            "billing.py",
            100,
            110,
            "class Invoice:\n    def __init__(self, lines):\n        self.lines = lines",
            37,
        ),
    ]
    out = render_user_message(diff=diff, retrieved_chunks=chunks)
    assert out.startswith("Relevant context from repository (top-2 chunks, total 79 tokens):")
    assert "billing.py (lines 10-24)" in out
    assert "billing.py (lines 100-110)" in out
    assert "End of repository context." in out
    # The diff block follows the context block.
    assert "```diff" in out
    assert out.index("Relevant context") < out.index("```diff")


def test_build_messages_passes_chunks_through():
    diff = "diff --git a/x.py b/x.py\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    chunks = [FakeChunk("a.py", 1, 5, "x = 1", 5)]
    msgs = build_messages(diff, retrieved_chunks=chunks)
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == SYSTEM_MESSAGE  # SYSTEM unchanged
    assert "Relevant context from repository" in msgs[1]["content"]


def test_build_messages_without_chunks_matches_v2_layout():
    diff = "diff --git a/x.py b/x.py\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    msgs = build_messages(diff)
    assert msgs[1]["content"] == USER_TEMPLATE.format(DIFF=diff)
