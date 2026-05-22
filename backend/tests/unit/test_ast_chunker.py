"""Unit tests for the cAST chunker (feature 015)."""

from __future__ import annotations

import pytest

from codesensei.indexing import ast_chunker
from codesensei.indexing.ast_chunker import (
    _count_tokens,
    chunk_with_treesitter,
)
from codesensei.indexing.chunker import dispatch_chunker


def test_python_simple_module():
    """T008: three top-level Python functions land in separate chunks (low target)."""
    src = (
        "def foo():\n    return 1\n\n"
        "def bar():\n    return 2\n\n"
        "def baz():\n    return 3\n"
    )
    out = chunk_with_treesitter(src, "python", "mod.py", target_tokens=5)
    assert out is not None
    assert len(out) == 3
    assert {c.language for c in out} == {"python"}
    assert [c.start_line for c in out] == [1, 4, 7]
    assert all(c.end_line >= c.start_line for c in out)
    assert "def foo" in out[0].content
    assert "def bar" in out[1].content
    assert "def baz" in out[2].content


def test_python_oversize_function_recursive_split():
    """T009: a class with multiple methods exceeds target → recursion splits into methods."""
    # Class > target_tokens. Inside: 5 small methods. Recurse → greedy merge.
    method = (
        "    def method_{n}(self, x, y):\n"
        "        # filler body line one\n"
        "        # filler body line two\n"
        "        return x + y\n"
    )
    class_src = "class Big:\n" + "".join(
        method.format(n=i) for i in range(5)
    )
    out = chunk_with_treesitter(class_src, "python", "big.py", target_tokens=20)
    assert out is not None
    assert len(out) > 1, "oversize class did not recurse into methods"
    assert all(c.language == "python" for c in out)
    # Every chunk content must be a non-empty source slice.
    assert all(c.content.strip() for c in out)


def test_typescript_basic():
    """T010: TS file with multiple declarations produces multiple structural chunks."""
    src = (
        "function alpha(x: number) { return x + 1; }\n"
        "function beta(y: number) { return y * 2; }\n"
        "class Gamma {\n"
        "  one() { return 1; }\n"
        "  two() { return 2; }\n"
        "}\n"
        "interface Delta { id: string }\n"
        "type Eps = number;\n"
    )
    out = chunk_with_treesitter(src, "typescript", "x.ts", target_tokens=10)
    assert out is not None
    assert len(out) >= 3, f"expected ≥3 TS chunks, got {len(out)}"
    assert {c.language for c in out} == {"typescript"}
    # First chunk must start at line 1.
    assert out[0].start_line == 1
    # No chunk spans more than the source length.
    assert all(c.end_line <= 8 for c in out)


def test_javascript_basic():
    """T011: JS file with function + arrow consts produces structural chunks."""
    src = (
        "function regular() { return 1; }\n"
        "const arrow = () => 2;\n"
        "const otherArrow = () => 3;\n"
        "class Container { method() { return 4; } }\n"
    )
    out = chunk_with_treesitter(src, "javascript", "x.js", target_tokens=8)
    assert out is not None
    assert len(out) >= 2
    assert {c.language for c in out} == {"javascript"}


def test_target_token_budget_respected_on_merge():
    """T012: 5 tiny Python functions merge to a single chunk under default target."""
    src = "".join(f"def f{i}(): return {i}\n" for i in range(5))
    out = chunk_with_treesitter(src, "python", "small.py")
    assert out is not None
    assert len(out) == 1, f"expected 1 merged chunk, got {len(out)}"
    assert out[0].language == "python"
    assert _count_tokens(out[0].content) < 1024


def test_imports_and_top_level_emitted_as_chunks():
    """T013: imports + module-level constant + function → ≥ 2 chunks."""
    src = (
        "import os\n"
        "import sys\n"
        "\n"
        "CONSTANT = 42\n"
        "\n"
        "def use_it():\n"
        "    return CONSTANT\n"
    )
    out = chunk_with_treesitter(src, "python", "mod.py", target_tokens=20)
    assert out is not None
    assert len(out) >= 2
    # The imports + constant region MUST be present in some chunk.
    joined = "\n".join(c.content for c in out)
    assert "import os" in joined
    assert "CONSTANT = 42" in joined
    assert "def use_it" in joined


def test_unsupported_language_falls_back_to_sliding(captured_log_events):
    """T020: unknown extension routes to sliding fallback with mode=sliding_no_extension."""
    src = "IDENTIFICATION DIVISION.\nPROGRAM-ID. HELLO.\nEND PROGRAM HELLO.\n"
    chunks = dispatch_chunker("foo.cobol", src)
    assert len(chunks) >= 1
    routing = [e for e in captured_log_events if e.get("event") == "chunker_routing"]
    assert len(routing) == 1
    assert routing[0]["mode"] == "sliding_no_extension"
    # Sliding fallback for "other" language emits language="other".
    assert chunks[0].language == "other"


def test_parse_failure_falls_back_to_sliding(captured_log_events, monkeypatch):
    """T021: simulated parser failure → mode=sliding_parse_failed, fallback runs."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated walker crash")

    monkeypatch.setattr(ast_chunker, "chunk_with_treesitter", boom)

    src = "function ok() { return 1 }\n"
    chunks = dispatch_chunker("broken.ts", src)
    assert len(chunks) >= 1
    routing = [e for e in captured_log_events if e.get("event") == "chunker_routing"]
    assert any(e["mode"] == "sliding_parse_failed" for e in routing)


def test_markdown_with_treesitter_grammar():
    """T025: markdown with two ## sections produces multiple chunks via AST grammar."""
    if not ast_chunker._grammar_available("markdown"):
        pytest.skip("tree-sitter-markdown grammar not available in this language pack")

    src = "# Title\n\nIntro paragraph.\n\n## Section A\n\nBody A.\n\n## Section B\n\nBody B.\n"
    out = chunk_with_treesitter(src, "markdown", "doc.md")
    assert out is not None
    assert len(out) >= 2
    assert all(c.language == "markdown" for c in out)
