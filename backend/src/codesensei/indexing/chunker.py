"""Language-aware chunking — Python AST, Markdown headings, sliding-window fallback."""
from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import aiofiles

# File-extension → language label. "other" is used for everything not enumerated.
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".md": "markdown",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
}

SUPPORTED_EXTS: frozenset[str] = frozenset(_EXT_TO_LANG)

MAX_FILE_BYTES = 200 * 1024  # 200 KB
NUL_PROBE_BYTES = 8 * 1024  # first 8 KB

SLIDING_WINDOW_LINES = 80
SLIDING_OVERLAP_LINES = 10
MARKDOWN_MAX_LINES = 200


@dataclass(frozen=True)
class ChunkSpec:
    """One chunk's positional + textual data, before embedding."""

    file_path: str
    language: str
    start_line: int
    end_line: int
    content: str


def language_for(path: Path) -> str:
    return _EXT_TO_LANG.get(path.suffix.lower(), "other")


def is_binary(probe: bytes) -> bool:
    """Detect binary content by presence of a NUL byte in the first N bytes."""
    return b"\x00" in probe


def iter_source_files(root: Path) -> Iterator[Path]:
    """Walk the tree, yielding paths to plausibly-textual source files.

    Skips: hidden directories (".git", ".venv", "node_modules", "__pycache__", "dist", "build"),
    files larger than 200 KB, files with unsupported extensions.
    """
    skip_dirs = {
        ".git", ".venv", "venv", "node_modules", "__pycache__",
        "dist", "build", ".idea", ".vscode",
    }
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        # bail out if any parent is in skip_dirs
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def chunk_python(content: str, file_path: str) -> list[ChunkSpec]:
    """Split a Python source file by top-level def/class; bundle stray statements."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Fall back to sliding window so we still index the file.
        return chunk_sliding(content, file_path, language="python")

    lines = content.splitlines()
    chunks: list[ChunkSpec] = []

    # Collect top-level def/class nodes (in source order).
    defs: list[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            defs.append((start, end))

    # "Module preamble" = everything before the first def/class (imports, constants, etc.).
    if defs:
        first_def_start = defs[0][0]
        if first_def_start > 1:
            preamble_end = first_def_start - 1
            text = "\n".join(lines[:preamble_end])
            if text.strip():
                chunks.append(
                    ChunkSpec(
                        file_path=file_path,
                        language="python",
                        start_line=1,
                        end_line=preamble_end,
                        content=text,
                    )
                )
        for start, end in defs:
            text = "\n".join(lines[start - 1 : end])
            chunks.append(
                ChunkSpec(
                    file_path=file_path,
                    language="python",
                    start_line=start,
                    end_line=end,
                    content=text,
                )
            )
    else:
        # No defs/classes at all → one chunk for the whole file.
        if content.strip():
            chunks.append(
                ChunkSpec(
                    file_path=file_path,
                    language="python",
                    start_line=1,
                    end_line=max(1, len(lines)),
                    content=content,
                )
            )
    return chunks


_MD_HEADING_RE = re.compile(r"^(#{1,2})\s", re.MULTILINE)


def chunk_markdown(content: str, file_path: str) -> list[ChunkSpec]:
    """Split Markdown on `#` and `##` boundaries; oversize sections fall back to sliding."""
    lines = content.splitlines()
    boundaries: list[int] = [0]
    for idx, line in enumerate(lines):
        if _MD_HEADING_RE.match(line + "\n") and idx != 0:
            boundaries.append(idx)
    boundaries.append(len(lines))

    chunks: list[ChunkSpec] = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        section_lines = lines[start:end]
        if not any(line.strip() for line in section_lines):
            continue
        if end - start > MARKDOWN_MAX_LINES:
            section_text = "\n".join(section_lines)
            sub = chunk_sliding(section_text, file_path, language="markdown")
            # Shift sub-chunk line numbers into the parent file's frame.
            for sc in sub:
                chunks.append(
                    ChunkSpec(
                        file_path=file_path,
                        language="markdown",
                        start_line=start + sc.start_line,
                        end_line=start + sc.end_line,
                        content=sc.content,
                    )
                )
        else:
            chunks.append(
                ChunkSpec(
                    file_path=file_path,
                    language="markdown",
                    start_line=start + 1,
                    end_line=end,
                    content="\n".join(section_lines),
                )
            )
    return chunks


def chunk_sliding(
    content: str,
    file_path: str,
    *,
    language: str | None = None,
    window: int = SLIDING_WINDOW_LINES,
    overlap: int = SLIDING_OVERLAP_LINES,
) -> list[ChunkSpec]:
    """Fixed-line sliding-window chunker with overlap. Skips empty files."""
    if language is None:
        language = language_for(Path(file_path))
    lines = content.splitlines()
    if not lines or not any(line.strip() for line in lines):
        return []
    chunks: list[ChunkSpec] = []
    step = max(1, window - overlap)
    i = 0
    n = len(lines)
    while i < n:
        end = min(n, i + window)
        text = "\n".join(lines[i:end])
        chunks.append(
            ChunkSpec(
                file_path=file_path,
                language=language,
                start_line=i + 1,
                end_line=end,
                content=text,
            )
        )
        if end == n:
            break
        i += step
    return chunks


def dispatch_chunker(file_path: str, content: str) -> list[ChunkSpec]:
    """Pick the right chunker by extension."""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".py":
        return chunk_python(content, file_path)
    if suffix == ".md":
        return chunk_markdown(content, file_path)
    return chunk_sliding(content, file_path)


async def read_text_safely(path: Path) -> str | None:
    """Read a file's full content as UTF-8 (lenient); return None for binary/unreadable files."""
    try:
        async with aiofiles.open(path, "rb") as fh:
            probe = await fh.read(NUL_PROBE_BYTES)
            if is_binary(probe):
                return None
            rest = await fh.read()
        raw = probe + rest
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return raw.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return None
    except OSError:
        return None


async def chunk_repo(root: Path) -> list[ChunkSpec]:
    """Walk `root` and produce all chunks for its source files.

    Empty-or-skipped files contribute nothing.
    """
    out: list[ChunkSpec] = []
    for path in iter_source_files(root):
        content = await read_text_safely(path)
        if content is None or not content.strip():
            continue
        rel = path.relative_to(root).as_posix()
        out.extend(dispatch_chunker(rel, content))
    return out


def count_source_files(root: Path) -> int:
    """Pre-scan: how many source files would be indexed (used by sync/async dispatcher)."""
    return sum(1 for _ in iter_source_files(root))
