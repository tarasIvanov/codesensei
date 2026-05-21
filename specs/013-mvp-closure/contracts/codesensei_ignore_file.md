# Contract: `.codesensei-ignore` file format + parser

**Status**: NEW. Introduced by feature 013.
**Surface**: filesystem artefact + Python module `backend/src/codesensei/indexing/ignore.py`.

## File format

- Plain UTF-8 text, located at `<repo_root>/.codesensei-ignore`.
- One pattern per line.
- A line whose first non-whitespace character is `#` is a comment.
- A blank line (after right-trim) is ignored.
- A trailing `/` marks the pattern as a directory pattern.
- A line not ending with `/` is a file/glob pattern.
- No negation (`!pattern`) — line is treated as literal glob if it starts with `!`.
- No escape sequences beyond what `fnmatch.fnmatchcase` honours.

**Hard caps**:
- Max file size: 4 KB. Files larger than 4 KB → parser returns `None` (= "no file"), emits warning `codesensei_ignore_oversize`.
- Max patterns: 200. If a file contains more usable lines, only the first 200 are kept; warning `codesensei_ignore_truncated` emitted.

## Module surface

```python
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class IgnoreSpec:
    patterns: tuple[str, ...]
    directory_flags: tuple[bool, ...]
    warnings: tuple[str, ...]


def parse_ignore_file(root: Path) -> IgnoreSpec | None:
    """Read <root>/.codesensei-ignore. Return None when the file does not
    exist or is effectively empty. Returns an IgnoreSpec on success.
    """


def path_matches_any(path: Path, spec: IgnoreSpec, root: Path) -> bool:
    """True iff `path` should be skipped per the parsed spec.

    File-pattern match (directory_flag=False):
      - fnmatch.fnmatchcase(path.relative_to(root).as_posix(), pattern), OR
      - fnmatch.fnmatchcase(path.name, pattern).

    Directory-pattern match (directory_flag=True):
      - any part in path.relative_to(root).parts matches the pattern via
        fnmatch.fnmatchcase.
    """
```

## Semantics table

| Line in file | Parsed pattern | Directory? | Matches `vendor/x.py` | Matches `src/dist/y.ts` | Matches `gen/api.generated.ts` |
|--------------|----------------|------------|-----------------------|--------------------------|-------------------------------|
| `vendor/` | `vendor` | True | ✓ | ✗ | ✗ |
| `dist/` | `dist` | True | ✗ | ✓ | ✗ |
| `*.generated.ts` | `*.generated.ts` | False | ✗ | ✗ | ✓ |
| `**/*.snap` | `**/*.snap` | False | ✗ (no `.snap`) | ✗ (no `.snap`) | ✗ |
| `# this is a comment` | (dropped) | — | — | — | — |
| `   ` (blank) | (dropped) | — | — | — | — |

## Invariants

- **Pure function**: `parse_ignore_file` is filesystem I/O; `path_matches_any` is pure compute.
- **Deterministic**: same file + same path → same result.
- **No exceptions on malformed input**: a single bad line never aborts the parse; oversize file → return None + warning; >200 patterns → truncate + warning. The indexer never raises from this module under any input.
- **Stdlib-only**: imports limited to `pathlib`, `fnmatch`, `dataclasses`, `structlog` (logging).

## Maintenance policy

- Editing the file format requires an ADR (would change operator-facing contract).
- Editing the hard caps (4 KB / 200) is a code change inside `ignore.py`; no ADR required (numeric tuning).
- New helpers (e.g. `serialise_patterns`) can be added without touching the public surface.
