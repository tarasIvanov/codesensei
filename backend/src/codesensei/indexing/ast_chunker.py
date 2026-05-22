"""cAST (Concrete-AST) chunker driven by tree-sitter-language-pack (feature 015)."""

from __future__ import annotations

from functools import cache, lru_cache
from typing import TYPE_CHECKING

import tiktoken

if TYPE_CHECKING:
    from codesensei.indexing.chunker import ChunkSpec

# Per-language label → tree-sitter-language-pack grammar name. Membership in
# the keys is the gatekeeper: an unknown label forces sliding fallback.
_LANG_LABEL_TO_GRAMMAR: dict[str, str] = {
    "python": "python",
    "typescript": "typescript",
    "javascript": "javascript",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "markdown": "markdown",
    "c": "c",
    "cpp": "cpp",
    "ruby": "ruby",
    "php": "php",
    "kotlin": "kotlin",
    "swift": "swift",
}

# Per-language splittable structural-declaration node kinds. Verified against
# tree-sitter-language-pack 1.8 grammars.
_NODE_TYPES_PER_LANG: dict[str, frozenset[str]] = {
    "python": frozenset(
        {"function_definition", "class_definition", "decorated_definition"}
    ),
    "typescript": frozenset(
        {
            "function_declaration",
            "class_declaration",
            "method_definition",
            "interface_declaration",
            "type_alias_declaration",
            "enum_declaration",
        }
    ),
    "javascript": frozenset(
        {
            "function_declaration",
            "class_declaration",
            "method_definition",
            "generator_function_declaration",
            "lexical_declaration",
        }
    ),
    "go": frozenset({"function_declaration", "method_declaration", "type_declaration"}),
    "rust": frozenset(
        {"function_item", "impl_item", "struct_item", "enum_item", "trait_item", "mod_item"}
    ),
    "java": frozenset(
        {
            "class_declaration",
            "method_declaration",
            "interface_declaration",
            "constructor_declaration",
            "enum_declaration",
        }
    ),
    "markdown": frozenset({"atx_heading", "setext_heading"}),
    "c": frozenset({"function_definition", "declaration"}),
    "cpp": frozenset(
        {"function_definition", "class_specifier", "struct_specifier", "namespace_definition"}
    ),
    "ruby": frozenset({"method", "class", "module", "singleton_method"}),
    "php": frozenset(
        {
            "function_definition",
            "method_declaration",
            "class_declaration",
            "interface_declaration",
            "trait_declaration",
        }
    ),
    "kotlin": frozenset({"function_declaration", "class_declaration", "object_declaration"}),
    "swift": frozenset({"function_declaration", "class_declaration", "protocol_declaration"}),
}

_DEFAULT_NODE_TYPES: frozenset[str] = frozenset(
    {"function_definition", "class_definition", "method_definition"}
)

DEFAULT_TARGET_TOKENS = 1024


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    """cl100k_base encoder, cached for process lifetime."""
    return tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    """Token count via cl100k_base. Exposed for tests."""
    return len(_encoder().encode(text))


@cache
def _get_parser(grammar_name: str):
    """Cached parser construction per grammar."""
    from tree_sitter_language_pack import get_parser

    return get_parser(grammar_name)


def _grammar_available(label: str) -> bool:
    """Probe whether the language pack ships a usable parser for `label`."""
    grammar = _LANG_LABEL_TO_GRAMMAR.get(label)
    if grammar is None:
        return False
    try:
        _get_parser(grammar)
        return True
    except Exception:  # noqa: BLE001
        return False


def chunk_with_treesitter(
    content: str,
    language: str,
    file_path: str,
    *,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
) -> list[ChunkSpec] | None:
    """Run cAST chunking for `content` in `language`.

    Returns:
      * `None` — caller MUST fall back to sliding window. Causes: unknown
        language label, grammar load / parse failure, no splittable subtrees
        in a non-empty source.
      * `[]` — only for empty / whitespace-only content.
      * non-empty list — successful cAST chunking.
    """
    if target_tokens <= 0:
        raise ValueError("target_tokens must be > 0")

    if not content or not content.strip():
        return []

    grammar = _LANG_LABEL_TO_GRAMMAR.get(language)
    if grammar is None:
        return None

    try:
        parser = _get_parser(grammar)
    except Exception:  # noqa: BLE001
        return None

    try:
        tree = parser.parse(content)
    except Exception:  # noqa: BLE001
        return None

    root = tree.root_node()
    src_bytes = content.encode("utf-8")
    node_types = _NODE_TYPES_PER_LANG.get(language, _DEFAULT_NODE_TYPES)

    try:
        chunks = _chunk_subtree(
            root,
            src_bytes,
            language=language,
            file_path=file_path,
            node_types=node_types,
            target_tokens=target_tokens,
        )
    except Exception:  # noqa: BLE001
        return None

    if not chunks:
        return None

    return chunks


def _find_top_splittables(parent, node_types: frozenset[str]) -> list:
    """DFS for outer-most splittable named descendants of `parent`.

    Yields one entry per splittable subtree in source order. Does NOT descend
    into a node once it's been identified as splittable — keeps the recursion
    a fixed level so a class is captured whole here, then recursed into
    separately if it exceeds the token budget.
    """
    out = []

    def walk(node) -> None:
        for i in range(node.named_child_count()):
            child = node.named_child(i)
            if child is None:
                continue
            if child.kind() in node_types:
                out.append(child)
            else:
                walk(child)
        return

    walk(parent)
    return out


def _chunk_subtree(
    parent_node,
    src_bytes: bytes,
    *,
    language: str,
    file_path: str,
    node_types: frozenset[str],
    target_tokens: int,
) -> list[ChunkSpec]:
    """Produce chunks for the source region covered by `parent_node`.

    Algorithm:
      1. Find outermost splittable subtrees inside parent.
      2. Walk them in source order; emit non-trivial inter-splittable gaps
         as their own chunks (preserves imports, module-level constants).
      3. Greedy-merge consecutive splittables up to `target_tokens`.
      4. On oversize splittable, recurse into it to find inner splittables;
         if none, emit as a single chunk (upstream `MAX_CHUNK_TOKENS` halver
         catches the rare oversize leaf).
    """
    from codesensei.indexing.chunker import ChunkSpec

    splittables = _find_top_splittables(parent_node, node_types)
    if not splittables:
        return []

    chunks: list[ChunkSpec] = []

    pending: list = []
    pending_tokens = 0
    pending_start_byte: int | None = None
    pending_end_byte: int | None = None
    pending_start_line: int | None = None
    pending_end_line: int | None = None

    def flush_pending() -> None:
        nonlocal pending, pending_tokens
        nonlocal pending_start_byte, pending_end_byte, pending_start_line, pending_end_line
        if pending:
            text = src_bytes[pending_start_byte:pending_end_byte].decode(
                "utf-8", errors="replace"
            )
            chunks.append(
                ChunkSpec(
                    file_path=file_path,
                    language=language,
                    start_line=pending_start_line,  # type: ignore[arg-type]
                    end_line=pending_end_line,  # type: ignore[arg-type]
                    content=text,
                )
            )
            pending = []
            pending_tokens = 0
            pending_start_byte = None
            pending_end_byte = None
            pending_start_line = None
            pending_end_line = None

    def emit_gap(b1: int, b2: int) -> None:
        if b1 >= b2:
            return
        text = src_bytes[b1:b2].decode("utf-8", errors="replace")
        if not text.strip():
            return
        flush_pending()
        sl = src_bytes[:b1].count(b"\n") + 1
        el_inclusive = src_bytes[: max(b1, b2 - 1)].count(b"\n") + 1
        chunks.append(
            ChunkSpec(
                file_path=file_path,
                language=language,
                start_line=sl,
                end_line=el_inclusive,
                content=text,
            )
        )

    prev_end_byte = parent_node.start_byte()
    for splittable in splittables:
        sb = splittable.start_byte()
        eb = splittable.end_byte()
        emit_gap(prev_end_byte, sb)

        text = src_bytes[sb:eb].decode("utf-8", errors="replace")
        toks = _count_tokens(text)
        sl = splittable.start_position().row + 1
        el = splittable.end_position().row + 1

        if toks > target_tokens:
            flush_pending()
            sub_chunks = _chunk_subtree(
                splittable,
                src_bytes,
                language=language,
                file_path=file_path,
                node_types=node_types,
                target_tokens=target_tokens,
            )
            if sub_chunks:
                chunks.extend(sub_chunks)
            else:
                chunks.append(
                    ChunkSpec(
                        file_path=file_path,
                        language=language,
                        start_line=sl,
                        end_line=el,
                        content=text,
                    )
                )
        else:
            if pending and pending_tokens + toks > target_tokens:
                flush_pending()
            if not pending:
                pending_start_byte = sb
                pending_start_line = sl
            pending.append(splittable)
            pending_end_byte = eb
            pending_end_line = el
            pending_tokens += toks

        prev_end_byte = eb

    flush_pending()
    emit_gap(prev_end_byte, parent_node.end_byte())

    return chunks
