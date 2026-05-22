# Phase 0 Research: AST-Based Chunking for All Supported Languages

**Feature**: 015 ast-chunker
**Date**: 2026-05-22

## R1. Choice of grammar distribution

**Decision**: Use `tree-sitter-language-pack` (prebuilt manylinux/macOS wheels bundling ~100 grammars, including `python`, `typescript`, `tsx`, `javascript`, `go`, `rust`, `java`, `markdown`, `c`, `cpp`, `c-sharp`, `ruby`, `php`, `swift`, `kotlin`).

**Rationale**:
- Drops the per-language grammar-management overhead. The alternative is one wheel per language (`tree-sitter-python`, `tree-sitter-typescript`, …), which multiplies the dependency footprint and forces FR-009-style maintenance every time a new language is added.
- Wheels ship native binaries → no `apt install build-essential` in the Dockerfile → preserves the single-command-deploy promise (Principle V).
- Exposes a uniform `get_parser(name) -> tree_sitter.Parser` factory; the per-language wiring inside our module collapses to a single dict lookup.

**Alternatives considered**:
- **Per-language wheels** (e.g. `tree-sitter-typescript`, `tree-sitter-go`, …). Rejected: ~12 separate deps for the FR-009 minimum, each with its own release cadence; image growth dominated by the wheels' shared toolchain duplication, not the grammars.
- **Building grammars at install time via `tree-sitter-cli`**. Rejected: violates the spirit of Principle V (a real build toolchain in the image) and adds 200–400 MB to the image; the wheel approach beats it on both axes.
- **Hand-writing per-language regex splitters** (the current Python path generalised). Rejected: brittle, language-coupled, and indistinguishable on the wire from the sliding-window fallback — defeats the whole differentiator.

## R2. Per-language splittable-node-type sets

**Decision**: code-internal `_NODE_TYPES_PER_LANG: dict[str, set[str]]` keyed on the full-name language label that already lives on `ChunkSpec.language`:

```python
_NODE_TYPES_PER_LANG: dict[str, set[str]] = {
    "python":     {"function_definition", "class_definition", "decorated_definition"},
    "typescript": {"function_declaration", "class_declaration", "method_definition",
                   "interface_declaration", "type_alias_declaration", "enum_declaration"},
    "javascript": {"function_declaration", "class_declaration", "method_definition",
                   "generator_function_declaration"},
    "go":         {"function_declaration", "method_declaration", "type_declaration"},
    "rust":       {"function_item", "impl_item", "struct_item", "enum_item",
                   "trait_item", "mod_item"},
    "java":       {"class_declaration", "method_declaration", "interface_declaration",
                   "constructor_declaration", "enum_declaration"},
    "markdown":   {"section", "atx_heading", "setext_heading"},  # used only if tree-sitter-markdown available
    "c":          {"function_definition", "declaration"},
    "cpp":        {"function_definition", "class_specifier", "struct_specifier",
                   "namespace_definition"},
    "ruby":       {"method", "class", "module", "singleton_method"},
    "php":        {"function_definition", "method_declaration", "class_declaration",
                   "interface_declaration", "trait_declaration"},
    "kotlin":     {"function_declaration", "class_declaration", "object_declaration"},
    "swift":      {"function_declaration", "class_declaration", "protocol_declaration"},
}
_DEFAULT_NODE_TYPES = {"function_definition", "class_definition", "method_definition"}
```

**Rationale**:
- Per `tree-sitter-language-pack`'s grammars (verified by walking `Parser.parse(...).root_node` on small fixtures), the listed types are the named nodes whose source range corresponds to "a declaration a reader would expect to see one of in a code-review chunk".
- Pure leaf nodes (`identifier`, `number`, `string`) are deliberately excluded — they are the recursion boundary, not chunk targets.
- The `_DEFAULT_NODE_TYPES` fallback ensures any registered grammar we haven't hand-mapped still produces reasonable structural chunks for the common case (most C-family grammars use `function_definition`; many OOP grammars use `class_definition`).

**Alternatives considered**:
- **One global set across all languages**. Rejected: `function_declaration` vs `function_definition` vs `function_item` is grammar-specific (TS vs C vs Rust); a global set would miss real declarations.
- **Auto-discovery from grammar's `node_types.json`** at startup. Rejected: brittle (some grammar wheels don't ship `node_types.json` next to the binary), and any heuristic for "is this a declaration node" is itself language-coupled. Hard-coding the maps is the honest path.

## R3. Parser construction cost

**Decision**: cache `tree_sitter_language_pack.get_parser(name)` at module scope via `functools.lru_cache(maxsize=None)`. Cache the `cl100k_base` tiktoken encoder via the same pattern.

**Rationale**:
- Parser construction wraps a CFFI-loaded native library; the construction itself is ~milliseconds on first call, < 100 µs on cache hit. For a 200-file repo with ~7 distinct languages, the construction cost is dominated by the tree walk by orders of magnitude.
- `tiktoken.get_encoding(...)` performs a network-free local lookup but allocates a `~3 MB` BPE table; caching saves both time and memory under repeated calls from `_count_tokens`.

**Alternatives considered**:
- **Per-call construction**. Rejected: pointless overhead.
- **Per-process pre-warm at app boot**. Rejected: pulls grammars we may never need for a given workload into RAM at the cost of startup latency. Lazy lru_cache is the right shape.

## R4. 1-based line anchoring

**Decision**: emit `start_line = node.start_point.row + 1`, `end_line = node.end_point.row + 1`. Both inclusive.

**Rationale**:
- Tree-sitter reports `Point(row, column)` where `row` is 0-based; our existing `ChunkSpec.start_line` / `end_line` contract is 1-based inclusive (see `chunk_python`).
- Adding 1 to both keeps the semantics identical to the current Python AST path (`node.lineno` is already 1-based, `end_lineno` is 1-based inclusive — same as our addition).
- For a node that spans a single line, `start_line == end_line`. For the "gap" case (no node, just whitespace + comments), we emit `start_line = previous.end_line + 1`, `end_line = next.start_line - 1` and only flush if the gap contains non-whitespace content.

**Alternatives considered**:
- **Byte-slice anchoring** (`content[node.start_byte : node.end_byte]`). Rejected as the source of truth for line numbers: the *content* of the chunk is derived from `node.text.decode("utf-8")` for correctness, but the line numbers used by the UI come from `start_point` / `end_point`.

## R5. cAST interplay with the upstream `MAX_CHUNK_TOKENS=7000` halver

**Decision**: target `~1024` tokens; on a single node bigger than the target, descend into named splittable children; on a leaf still bigger than the target, emit it as-is and rely on the upstream halver. The chunker NEVER slices mid-line.

**Rationale**:
- The upstream halver in `review/service.py` is the LAST-RESORT hard cap for the LLM prompt context. It exists precisely because the chunker cannot guarantee semantic bounds. By aiming low (~1024) the halver should fire on `<1 %` of chunks in the common case (SC-002).
- Mid-line slicing in the chunker would corrupt the source content shown back to the user in the review UI; the upstream halver halves *by chunk*, not by byte, so it doesn't have this problem.
- Greedy merging is the dual: tiny adjacent declarations get bundled so the index doesn't balloon with one-function chunks for utility modules (e.g. a Python `__init__.py` with three re-export lines + two helpers).

**Alternatives considered**:
- **Drop the upstream halver, push the hard cap into the chunker**. Rejected: the halver also catches non-AST paths (Markdown headings, sliding-window), so removing it would create gaps.
- **Target == hard cap = 7000**. Rejected: leaves no slack for the prompt template + retrieval overhead at LLM-call time; the existing setup is well-tuned and orthogonal to this feature.

## R6. `ChunkSpec.language` label under the new path

**Decision**: keep the existing full-name labels (`"python"`, `"typescript"`, `"javascript"`, `"go"`, `"rust"`, `"java"`, `"markdown"`, `"c"`, `"cpp"`, `"ruby"`, `"php"`, `"kotlin"`, `"swift"`, etc.) on `ChunkSpec.language`. Internal mapping from label → grammar name (`_LANG_LABEL_TO_GRAMMAR`) is the only place the `tree-sitter-language-pack` short names appear.

**Rationale**:
- The existing `language_for()` helper already returns full-name labels; the downstream vector store and retrieval code consume `ChunkSpec.language` as-is. Changing the label format is an unnecessary breaking change.
- Within the new module, `_LANG_LABEL_TO_GRAMMAR = {"typescript": "typescript", "tsx": "tsx", "javascript": "javascript", "python": "python", "markdown": "markdown", "c-sharp": "csharp", …}` translates at the boundary.

**Alternatives considered**:
- **Short labels (`"py"`, `"ts"`)**. Rejected: existing fixtures, tests, and downstream UIs already display the full names; changing them now is a noisy diff with no functional gain.

## R7. Markdown handling under the new chunker

**Decision**: if `tree-sitter-language-pack` ships a `markdown` grammar (it does — sometimes as `tree-sitter-markdown` packaged within the pack), use it via the same `chunk_with_treesitter(...)` path with the `{section, atx_heading, setext_heading}` splittable set; otherwise fall through to the existing `chunk_markdown` heading splitter (kept verbatim in `chunker.py`).

**Rationale**:
- The current heading splitter is reasonable and well-tested. Replacing it with `tree-sitter-markdown` is a refinement, not a critical-path fix.
- The fallback path is the safety net if the language pack ever ships without the markdown grammar, or if a `.md` file has malformed structure tree-sitter cannot parse.

**Alternatives considered**:
- **Drop the heading splitter, force tree-sitter-markdown only**. Rejected: removes a known-good baseline for negligible benefit.

## R8. Test-vs-production tree-sitter parity

**Decision**: production code and unit tests both pull grammars from the same `tree-sitter-language-pack` install. Tests do not pre-build grammars or mock the parser.

**Rationale**:
- Mocking the parser would mean the tests verify the dispatcher logic but NOT that the per-language node-type sets actually match the grammar's emitted node types — defeating the purpose.
- The language pack is a regular pip dep; CI installs it once and reuses it across the suite. Test suite runtime impact: ~50 ms one-time parser construction per language touched.

**Alternatives considered**:
- **Mock `chunk_with_treesitter` in `test_indexing_chunker.py`** at the boundary. Rejected for `test_ast_chunker.py` (need real behaviour) but ACCEPTABLE in the existing chunker test for cases that only verify routing without caring about chunk content.
