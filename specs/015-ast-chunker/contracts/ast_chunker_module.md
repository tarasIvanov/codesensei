# Module Contract: `codesensei.indexing.ast_chunker`

**Feature**: 015 ast-chunker
**Date**: 2026-05-22
**Module location**: `backend/src/codesensei/indexing/ast_chunker.py` (NEW)

This is an **internal Python module contract** — not a wire-format. The module is a private collaborator of `chunker.py` and its surface is consumed only by `dispatch_chunker(...)` and tests.

## Exported surface

### `chunk_with_treesitter(content, language, *, target_tokens=1024) -> list[ChunkSpec] | None`

**Signature**:

```python
def chunk_with_treesitter(
    content: str,
    language: str,
    *,
    target_tokens: int = 1024,
) -> list[ChunkSpec] | None:
    ...
```

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `content` | `str` | yes | Full UTF-8 source of one file. Must be the same content that `dispatch_chunker` was handed; no normalisation beyond what the caller already did (e.g. encoding errors are out of scope here — `read_text_safely` upstream already replaced invalid sequences). |
| `language` | `str` | yes | The `ChunkSpec.language` label as returned by `language_for(path)` — full-name (e.g. `"typescript"`, `"python"`, `"markdown"`). NOT the tree-sitter grammar name; the module performs the translation internally via `_LANG_LABEL_TO_GRAMMAR`. |
| `target_tokens` | `int` | no | Greedy-merge ceiling for the cAST algorithm. Default `1024`. Token measurement uses `cl100k_base`. |

**Returns**:

- `list[ChunkSpec]` (possibly empty if and only if `content` is empty / whitespace-only — same semantics as the existing `chunk_python` / `chunk_sliding` on empty input) when AST chunking succeeds.
- `None` when chunking SHOULD fall back to the sliding window. Specifically:
  - `language` is not present in `_LANG_LABEL_TO_GRAMMAR` (no grammar registered for the label).
  - `get_parser(...)` raised (grammar load failure).
  - `parser.parse(...)` produced a root node whose `has_error` is True AND no splittable subtrees survived the walk (i.e. the AST was so corrupted that there is nothing structural to emit).
  - The walker raised any other `Exception` during tree traversal.

The caller (`dispatch_chunker`) MUST treat `None` as "fall back to sliding window" and emit the appropriate routing log event.

**Side effects**:

- May call `tiktoken.get_encoding("cl100k_base")` once per process (cached). No file I/O. No network.
- May log at `structlog` `debug` level for internal trace ("cAST started", "cAST emitted N chunks"). No log entry at `info` or above — routing-level logging is the caller's job.

**Performance**:

- O(N) in the size of the source tree's named nodes, plus O(M) tiktoken encodings where M is the count of candidate merge points. Cached parser + encoder amortise startup costs across calls.
- For a 1000-line TypeScript file with ~50 declarations, target latency is < 50 ms on the dev machine.

### `_count_tokens(text: str) -> int`

Helper exposed to tests:

```python
def _count_tokens(text: str) -> int:
    """Count tokens in `text` using the cached cl100k_base encoder.

    Module-private by underscore convention; exposed so tests can compute the
    same value the chunker uses when constructing oversize fixtures.
    """
```

**Behaviour**: deterministic; same input always returns the same int. Cached encoder lifetime is the process.

### `_NODE_TYPES_PER_LANG: dict[str, frozenset[str]]`

Read-only at runtime; mutation by callers is forbidden. See `data-model.md` and `research.md §R2` for the literal value.

### `_LANG_LABEL_TO_GRAMMAR: dict[str, str]`

Read-only at runtime. Membership in the keys is the gatekeeper: a `language_for()` label not in this dict means "no AST attempt → sliding fallback with `mode="sliding_no_grammar"`".

## Caller contract (`chunker.py`)

The rewired `dispatch_chunker(file_path, content)` MUST behave per this routing rule:

```python
def dispatch_chunker(file_path: str, content: str) -> list[ChunkSpec]:
    lang = language_for(Path(file_path))   # full-name label or "other"
    log = structlog.get_logger("indexing.chunker")

    if lang == "other":
        log.info("chunker_routing", path=file_path, lang=lang, mode="sliding_no_extension")
        return chunk_sliding(content, file_path)

    if lang not in _LANG_LABEL_TO_GRAMMAR:
        log.info("chunker_routing", path=file_path, lang=lang, mode="sliding_no_grammar")
        return chunk_sliding(content, file_path)

    try:
        chunks = chunk_with_treesitter(content, lang)
    except Exception:  # noqa: BLE001 — broad by design, fallback is the safety net
        log.info("chunker_routing", path=file_path, lang=lang, mode="sliding_parse_failed",
                 exc_info=True)
        return chunk_sliding(content, file_path)

    if chunks is None:
        log.info("chunker_routing", path=file_path, lang=lang, mode="sliding_parse_failed")
        return chunk_sliding(content, file_path)

    log.info("chunker_routing", path=file_path, lang=lang, mode="ast", count=len(chunks))
    return chunks
```

**Routing-event contract**:

- Event name: `"chunker_routing"`.
- Required keys: `path` (str), `lang` (str), `mode` (one of `"ast" | "sliding_no_grammar" | "sliding_parse_failed" | "sliding_no_extension"`).
- Optional keys: `count` (int, only when `mode == "ast"`), `exc_info=True` (only when an exception was caught).
- Level: `info`.
- Logger name: `"indexing.chunker"`.

**Per-run summary contract** (emitted by `chunk_repo` at the end of a run):

- Event name: `"chunker_run_summary"`.
- Required keys: `total` (int), `by_mode: dict[str, int]` (e.g. `{"ast": 142, "sliding_no_grammar": 3, "sliding_parse_failed": 1, "sliding_no_extension": 0}`).
- Level: `info`.
- Logger name: `"indexing.chunker"`.

## ChunkSpec emission contract

Under the AST path:

| Field | Constraint |
|-------|------------|
| `file_path` | Same value the caller passed in. |
| `language` | Equals the `language` argument (full-name label). NEVER `None` under the AST path. |
| `start_line` | `>= 1`; equals `node.start_point.row + 1` (or the first merged node's value). |
| `end_line` | `>= start_line`; equals `node.end_point.row + 1` (or the last merged node's value). |
| `content` | Non-empty. Equals the raw source slice for the merged group (or for a single node, `bytes_buf[start_byte:end_byte].decode("utf-8")`). |

**Ordering**: chunks are emitted in source order. Adjacent chunks NEVER share start/end lines (no overlap in the AST path; the sliding fallback retains its existing overlap behaviour).

**Coverage**: for any non-whitespace region of the source, AT LEAST one chunk MUST include some part of that region; the gap-emission rule (research §R4) ensures imports, module-level constants, and module docstrings are never silently dropped. The chunker does NOT guarantee 100% byte coverage — comments between two adjacent declarations that fit on the boundary line may or may not appear, depending on which side of `start_point` they fall.

## Errors not raised

`chunk_with_treesitter` MUST NOT raise for any of these conditions — it MUST return `None` instead:

- Unknown `language` label.
- Grammar load failure for a known label.
- Any tree-sitter API exception during parsing or walking.
- Empty splittable-node set after the walk.

`chunk_with_treesitter` MAY raise for genuine programmer errors:

- `content` is not a `str`.
- `target_tokens <= 0`.

The caller does NOT catch these — they bubble up and fail the indexing job. They should never occur in production.
