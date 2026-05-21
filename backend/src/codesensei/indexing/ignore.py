"""`.codesensei-ignore` parser + matcher (feature 013, FR-4.3)."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

import structlog

_logger = structlog.get_logger(__name__)

IGNORE_FILE_NAME = ".codesensei-ignore"
MAX_FILE_BYTES = 4 * 1024
MAX_PATTERNS = 200


@dataclass(frozen=True)
class IgnoreSpec:
    patterns: tuple[str, ...]
    directory_flags: tuple[bool, ...]
    warnings: tuple[str, ...]


def parse_ignore_file(root: Path, *, repo_id: str | None = None) -> IgnoreSpec | None:
    path = root / IGNORE_FILE_NAME
    if not path.is_file():
        return None
    try:
        raw_bytes = path.read_bytes()
    except OSError:
        return None
    if len(raw_bytes) > MAX_FILE_BYTES:
        _logger.warning(
            "codesensei_ignore_oversize",
            repo_id=repo_id,
            file_bytes=len(raw_bytes),
            limit=MAX_FILE_BYTES,
        )
        return None
    text = raw_bytes.decode("utf-8", errors="replace")
    patterns: list[str] = []
    directory_flags: list[bool] = []
    total_usable_lines = 0
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if line.endswith("/"):
            normalised = line.rstrip("/").strip()
            if not normalised:
                continue
            total_usable_lines += 1
            if len(patterns) < MAX_PATTERNS:
                patterns.append(normalised)
                directory_flags.append(True)
        else:
            normalised = line.strip()
            if not normalised:
                continue
            total_usable_lines += 1
            if len(patterns) < MAX_PATTERNS:
                patterns.append(normalised)
                directory_flags.append(False)
    if not patterns:
        return None
    warnings: list[str] = []
    if total_usable_lines > MAX_PATTERNS:
        warnings.append("codesensei_ignore_truncated")
        _logger.warning(
            "codesensei_ignore_truncated",
            repo_id=repo_id,
            total_lines=total_usable_lines,
            kept=MAX_PATTERNS,
        )
    return IgnoreSpec(
        patterns=tuple(patterns),
        directory_flags=tuple(directory_flags),
        warnings=tuple(warnings),
    )


def path_matches_any(path: Path, spec: IgnoreSpec, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    rel_posix = rel.as_posix()
    parts = rel.parts
    name = path.name
    for pattern, is_dir in zip(spec.patterns, spec.directory_flags, strict=True):
        if is_dir:
            if any(fnmatch.fnmatchcase(part, pattern) for part in parts):
                return True
        else:
            if fnmatch.fnmatchcase(rel_posix, pattern):
                return True
            if fnmatch.fnmatchcase(name, pattern):
                return True
    return False


__all__ = [
    "IGNORE_FILE_NAME",
    "MAX_FILE_BYTES",
    "MAX_PATTERNS",
    "IgnoreSpec",
    "parse_ignore_file",
    "path_matches_any",
]
