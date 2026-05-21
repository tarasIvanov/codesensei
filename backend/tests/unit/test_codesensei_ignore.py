"""Unit tests for indexing/ignore.py (feature 013)."""

from __future__ import annotations

from pathlib import Path

from codesensei.indexing.ignore import (
    IGNORE_FILE_NAME,
    MAX_FILE_BYTES,
    MAX_PATTERNS,
    parse_ignore_file,
    path_matches_any,
)


def _write_ignore(tmp_path: Path, body: str) -> None:
    (tmp_path / IGNORE_FILE_NAME).write_text(body, encoding="utf-8")


def test_missing_file_returns_none(tmp_path: Path):
    assert parse_ignore_file(tmp_path) is None


def test_happy_path_three_patterns(tmp_path: Path):
    _write_ignore(tmp_path, "vendor/\n*.generated.ts\ndist/\n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    assert spec.patterns == ("vendor", "*.generated.ts", "dist")
    assert spec.directory_flags == (True, False, True)
    assert spec.warnings == ()


def test_comments_and_blanks_dropped(tmp_path: Path):
    _write_ignore(
        tmp_path,
        "# top comment\n\nvendor/\n   \n# inline\n*.snap\n\n",
    )
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    assert spec.patterns == ("vendor", "*.snap")
    assert spec.directory_flags == (True, False)


def test_only_comments_returns_none(tmp_path: Path):
    _write_ignore(tmp_path, "# a\n# b\n\n")
    assert parse_ignore_file(tmp_path) is None


def test_trailing_whitespace_stripped(tmp_path: Path):
    _write_ignore(tmp_path, "vendor/   \n*.snap  \n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    assert spec.patterns == ("vendor", "*.snap")
    assert spec.directory_flags == (True, False)


def test_truncation_at_max_patterns(tmp_path: Path):
    lines = [f"skip-{i}/" for i in range(MAX_PATTERNS + 50)]
    _write_ignore(tmp_path, "\n".join(lines) + "\n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    assert len(spec.patterns) == MAX_PATTERNS
    assert spec.warnings == ("codesensei_ignore_truncated",)


def test_oversize_file_returns_none(tmp_path: Path):
    body = "a/\n" * (MAX_FILE_BYTES + 100)
    _write_ignore(tmp_path, body)
    assert parse_ignore_file(tmp_path) is None


def test_match_directory_pattern(tmp_path: Path):
    _write_ignore(tmp_path, "vendor/\n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    assert path_matches_any(tmp_path / "vendor" / "x.py", spec, tmp_path) is True
    assert path_matches_any(tmp_path / "src" / "vendor" / "y.py", spec, tmp_path) is True
    assert path_matches_any(tmp_path / "src" / "main.py", spec, tmp_path) is False


def test_match_filename_glob(tmp_path: Path):
    _write_ignore(tmp_path, "*.generated.ts\n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    assert path_matches_any(tmp_path / "src" / "api.generated.ts", spec, tmp_path) is True
    assert path_matches_any(tmp_path / "deep" / "nest" / "x.generated.ts", spec, tmp_path) is True
    assert path_matches_any(tmp_path / "src" / "api.ts", spec, tmp_path) is False


def test_match_snap_filename(tmp_path: Path):
    _write_ignore(tmp_path, "*.snap\n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    assert path_matches_any(tmp_path / "tests" / "foo.snap", spec, tmp_path) is True


def test_match_dist_dir(tmp_path: Path):
    _write_ignore(tmp_path, "dist/\n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    assert path_matches_any(tmp_path / "dist" / "main.js", spec, tmp_path) is True
    assert path_matches_any(tmp_path / "packages" / "a" / "dist" / "x.js", spec, tmp_path) is True
    assert path_matches_any(tmp_path / "src" / "main.ts", spec, tmp_path) is False


def test_path_outside_root_returns_false(tmp_path: Path):
    _write_ignore(tmp_path, "vendor/\n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    # Path not relative to root → safe-False
    assert path_matches_any(Path("/somewhere/else/vendor/x.py"), spec, tmp_path) is False


def test_directory_pattern_with_trailing_only_slash_dropped(tmp_path: Path):
    _write_ignore(tmp_path, "/\nvendor/\n")
    spec = parse_ignore_file(tmp_path)
    # The bare "/" line normalises to empty + is dropped.
    assert spec is not None
    assert spec.patterns == ("vendor",)


def test_iter_source_files_skips_matched_paths(tmp_path: Path):
    """Integration of ignore spec with iter_source_files (feature 013 FR-003)."""
    from codesensei.indexing.chunker import iter_source_files

    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "skip.py").write_text("x = 1\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "keep.py").write_text("y = 2\n")
    (tmp_path / "src" / "api.generated.ts").write_text("export {}\n")
    _write_ignore(tmp_path, "vendor/\n*.generated.ts\n")
    spec = parse_ignore_file(tmp_path)
    assert spec is not None
    walked = iter_source_files(tmp_path, extra_skip_globs=spec)
    paths = sorted(p.relative_to(tmp_path).as_posix() for p in walked)
    assert paths == ["src/keep.py"]

