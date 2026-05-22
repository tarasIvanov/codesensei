# Phase 1 Data Model: AST-Based Chunking

**Feature**: 015 ast-chunker
**Date**: 2026-05-22

## Overview

This feature introduces **no database schema change**. The existing `code_chunks` table column shape is unchanged — only the content emitted into the existing columns changes for non-Python files.

## Persisted Entities (unchanged)

### `code_chunks` (existing — feature 005)

The schema as of feature 005 / alembic revision `003_repos_chunks` continues to apply unchanged:

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | unchanged |
| `repo_id` | UUID FK→`repos` | unchanged |
| `file_path` | TEXT | unchanged — repo-relative posix path |
| `language` | TEXT | unchanged — full-name label per `_EXT_TO_LANG` (`"python"`, `"typescript"`, …); `None`/`"other"` only when sliding-window fallback fires on an unknown extension |
| `start_line` | INTEGER | unchanged — 1-based inclusive |
| `end_line` | INTEGER | unchanged — 1-based inclusive |
| `content` | TEXT | unchanged — raw source text of the chunk |
| `token_count` | INTEGER | unchanged — `cl100k_base` token count of `content` |
| `embedding` | `vector(dim)` | unchanged — produced downstream by the embedding adapter |

**Migration**: NONE. No `alembic revision` is generated for feature 015.

## Code-internal Entities (new)

### `ChunkRoutingMode` (Python `Literal`)

A code-internal `Literal["ast", "sliding_no_grammar", "sliding_parse_failed", "sliding_no_extension"]` used as the `mode` field on the structured-log `chunker_routing` event (FR-001, FR-008).

| Mode | Meaning |
|------|---------|
| `"ast"` | `chunk_with_treesitter(content, language)` returned a non-empty list of chunks. |
| `"sliding_no_grammar"` | The file's `language_for()` label is not in `_LANG_LABEL_TO_GRAMMAR`; AST path was never attempted. |
| `"sliding_parse_failed"` | The AST path was attempted but raised an exception or returned `None` (grammar load failure, syntax errors past recovery, walker exhausted). The broad `except Exception` in `dispatch_chunker` catches it. |
| `"sliding_no_extension"` | Included in the taxonomy for completeness; the file would normally never reach `dispatch_chunker` because `iter_source_files` already filters on `SUPPORTED_EXTS`. Emitted only if `dispatch_chunker` is called directly (e.g. from tests) with an unsupported extension. |

**Persistence**: none. This is a structured-log field only.

### `_NODE_TYPES_PER_LANG` (Python `dict[str, frozenset[str]]`)

Code-internal map from `ChunkSpec.language` label → the set of grammar node types that count as splittable structural declarations. Initial population covers FR-009 minimum (Python, TypeScript, JavaScript, Go, Rust, Java, Markdown) plus the C-family and a few others; see `research.md` §R2 for the full literal. Default fallback `_DEFAULT_NODE_TYPES` applies to any registered grammar without a hand-mapped set.

**Persistence**: none. Lives as a module-level constant in `ast_chunker.py`; new languages are added by editing this dict (one-line code change, no migration).

**Validation**: implicitly enforced by the cAST walker — a node whose type is not in the relevant set is descended into during the recursive split but is not itself emitted as a chunk boundary.

### `_LANG_LABEL_TO_GRAMMAR` (Python `dict[str, str]`)

Code-internal map from `ChunkSpec.language` label → `tree-sitter-language-pack` grammar name. Most entries are identity (`"python" → "python"`, `"typescript" → "typescript"`), with a few translations (`"csharp"` if we keep that label, `"c-sharp"` per language-pack convention). The key insight: this dict is the **gatekeeper** — a label that is not a key here forces the sliding-window fallback, even if a grammar technically exists in the language pack.

**Persistence**: none.

### `ChunkSpec` (existing — unchanged)

```python
@dataclass(frozen=True)
class ChunkSpec:
    file_path: str
    language: str            # full-name label, unchanged
    start_line: int          # 1-based inclusive
    end_line: int            # 1-based inclusive
    content: str
```

Field-by-field semantics under the new path:

| Field | Source under cAST | Source under sliding fallback (unchanged) |
|-------|-------------------|-------------------------------------------|
| `file_path` | repo-relative posix path passed from `chunk_repo` | same |
| `language` | the full-name label that drove the dispatch (`"python"`, `"typescript"`, …) | the full-name label or `"other"` if the extension is unknown |
| `start_line` | `node.start_point.row + 1` (or the merged group's first node's value) | `i + 1` where `i` is the sliding-window start index |
| `end_line` | `node.end_point.row + 1` (or the merged group's last node's value) | `min(n, i + window)` |
| `content` | `bytes_buf[node.start_byte : node.end_byte].decode("utf-8")` (or concatenation of merged nodes' content); for gap chunks, the source slice between adjacent splittable siblings | `"\n".join(lines[i:end])` |

## Transitions / State Machine

Per-file routing (executed once per file by `dispatch_chunker`):

```
        ┌─────────────────────────────────────┐
        │  dispatch_chunker(file_path, content) │
        └────────────────┬────────────────────┘
                         │
                  language = language_for(path)
                         │
              ┌──────────┴───────────┐
              │ label in              │
              │ _LANG_LABEL_TO_GRAMMAR │
              └──────────┬───────────┘
              yes        │        no
                ┌────────┴────────┐
                │                 │
         try cAST            ─→ mode="sliding_no_grammar"
                │                 │
         ┌──────┴──────┐          │
         │ result?      │          │
         └──────┬──────┘          │
       chunks  │  None / Exception │
                │                 │
   mode="ast"   │   mode=          │
                │   "sliding_      │
                │    parse_failed" │
                │                 │
                ├─────────────────┤
                │                 │
              return chunks   return chunk_sliding(...)
              (cAST path)     (sliding fallback)
```

**Invariant**: every successful call to `dispatch_chunker(file_path, content)` for a non-empty content string produces ≥ 1 `ChunkSpec`. The sliding-window fallback guarantees this even if cAST returns an empty list (treated as "AST produced nothing useful" → fall back).

## Out-of-scope Entities

- **Per-language overrides via Settings UI**: not modelled. The maps are code-internal; configurability is deferred (spec §Out of scope).
- **Persisted chunk-mode column on `code_chunks`**: not modelled. Routing is observable via logs only — adding a column would be a Principle II hard trigger, justified only if downstream consumers need the mode at query time, which they don't in v1.
- **Re-embedding background job**: not modelled. Existing repos keep their old chunks until the user clicks **Re-index**.
