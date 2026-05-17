"""US1 unit tests: language-aware chunking."""
from __future__ import annotations

from pathlib import Path

import pytest

from codesensei.indexing.chunker import (
    MARKDOWN_MAX_LINES,
    SLIDING_OVERLAP_LINES,
    SLIDING_WINDOW_LINES,
    chunk_markdown,
    chunk_python,
    chunk_repo,
    chunk_sliding,
    count_source_files,
    dispatch_chunker,
    is_binary,
    iter_source_files,
    language_for,
)


def test_language_for_known_extensions():
    assert language_for(Path("a.py")) == "python"
    assert language_for(Path("a.md")) == "markdown"
    assert language_for(Path("a.ts")) == "typescript"
    assert language_for(Path("a.unknown")) == "other"


def test_is_binary_nul_byte():
    assert is_binary(b"hello\x00world") is True
    assert is_binary(b"plain text") is False


def test_chunk_python_emits_one_chunk_per_top_level_def_and_class():
    src = (
        "import os\n"
        "import sys\n"
        "\n"
        "VERSION = '1.0'\n"
        "\n"
        "def foo(x):\n"
        "    return x + 1\n"
        "\n"
        "class Bar:\n"
        "    def method(self):\n"
        "        pass\n"
    )
    chunks = chunk_python(src, "module.py")
    assert len(chunks) == 3  # preamble + foo + Bar
    assert chunks[0].start_line == 1
    assert chunks[0].end_line >= 4
    assert "import os" in chunks[0].content
    assert "def foo" in chunks[1].content
    assert "class Bar" in chunks[2].content
    # 1-indexed line numbers
    for c in chunks:
        assert c.start_line >= 1
        assert c.end_line >= c.start_line


def test_chunk_python_falls_back_to_sliding_on_syntax_error():
    src = "def broken(\n  this is not python\n  for line in range(\n"
    chunks = chunk_python(src, "broken.py")
    assert len(chunks) >= 1
    assert chunks[0].language == "python"


def test_chunk_python_no_defs_returns_single_chunk():
    src = "x = 1\ny = 2\nz = 3\n"
    chunks = chunk_python(src, "config.py")
    assert len(chunks) == 1
    assert chunks[0].content == src.rstrip("\n") or chunks[0].content == src
    assert chunks[0].start_line == 1


def test_chunk_markdown_splits_on_headings():
    src = (
        "# Title\n"
        "\n"
        "intro paragraph\n"
        "\n"
        "## Section A\n"
        "\n"
        "section a body\n"
        "\n"
        "## Section B\n"
        "\n"
        "section b body\n"
    )
    chunks = chunk_markdown(src, "README.md")
    # One per heading boundary.
    assert len(chunks) == 3
    assert "Title" in chunks[0].content
    assert "Section A" in chunks[1].content
    assert "Section B" in chunks[2].content


def test_chunk_markdown_oversize_falls_back_to_sliding():
    body = "\n".join([f"line {i}" for i in range(MARKDOWN_MAX_LINES + 50)])
    src = f"## Big\n{body}\n"
    chunks = chunk_markdown(src, "huge.md")
    assert len(chunks) >= 2  # sliding split into multiple
    for c in chunks:
        assert c.language == "markdown"
        assert c.start_line >= 1


def test_chunk_sliding_window_and_overlap():
    lines = [f"line {i}" for i in range(1, 200 + 1)]
    src = "\n".join(lines) + "\n"
    chunks = chunk_sliding(src, "big.ts")
    # 200 lines / step=70 → ceil(200/70) = 3 windows. Allow ±1 for boundary handling.
    assert 2 <= len(chunks) <= 4
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == SLIDING_WINDOW_LINES
    # Window 2 should overlap window 1 by SLIDING_OVERLAP_LINES.
    assert chunks[1].start_line == SLIDING_WINDOW_LINES - SLIDING_OVERLAP_LINES + 1


def test_chunk_sliding_empty_returns_nothing():
    assert chunk_sliding("", "empty.ts") == []
    assert chunk_sliding("\n\n\n", "blank.ts") == []


def test_dispatch_chunker_routes_by_extension():
    py = dispatch_chunker("a.py", "def f(): pass\n")
    md = dispatch_chunker("a.md", "## X\nbody\n")
    other = dispatch_chunker("a.ts", "const x = 1;\n")
    assert py and py[0].language == "python"
    assert md and md[0].language == "markdown"
    assert other and other[0].language == "typescript"


def test_iter_source_files_skips_hidden_and_unsupported(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored")
    (tmp_path / "code.py").write_text("x = 1\n")
    (tmp_path / "doc.md").write_text("# Hi\n")
    (tmp_path / "image.png").write_bytes(b"PNG\x00")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("module.exports = 1;\n")
    big = tmp_path / "big.ts"
    big.write_text("x\n" * 200_000)  # well over 200 KB

    paths = sorted(p.name for p in iter_source_files(tmp_path))
    assert "code.py" in paths
    assert "doc.md" in paths
    assert "config" not in paths
    assert "lib.js" not in paths
    assert "image.png" not in paths
    assert "big.ts" not in paths


def test_count_source_files_matches_iter(tmp_path: Path):
    (tmp_path / "a.py").write_text("a = 1\n")
    (tmp_path / "b.md").write_text("# b\n")
    (tmp_path / "c.cpp").write_text("int main(){return 0;}\n")
    assert count_source_files(tmp_path) == 3


@pytest.mark.asyncio
async def test_chunk_repo_skips_binary_and_blank(tmp_path: Path):
    (tmp_path / "ok.py").write_text("def foo(): return 1\n")
    (tmp_path / "binary.md").write_bytes(b"\x00\x01\x02 not text")
    (tmp_path / "blank.ts").write_text("\n\n\n")
    chunks = await chunk_repo(tmp_path)
    assert any(c.file_path == "ok.py" for c in chunks)
    assert not any(c.file_path == "binary.md" for c in chunks)
    assert not any(c.file_path == "blank.ts" for c in chunks)
