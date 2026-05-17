"""Verbatim prompt template (frozen by contracts/llm_prompt_v3.md; SYSTEM unchanged from v2)."""

# ruff: noqa: E501  -- prompt template is contract-frozen; reflowing changes meaning.
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from codesensei.providers.base import ChatMessage


class _ChunkLike(Protocol):
    file_path: str
    start_line: int
    end_line: int
    content: str
    token_count: int


SYSTEM_MESSAGE = """\
You are a senior code reviewer. You receive a single unified diff and respond with a structured JSON review. You MUST follow these rules without exception:

1. Output ONLY a single JSON object. No prose before, no prose after, no markdown fences.
2. The JSON object MUST conform to this exact schema:
   {
     "verdict": "approve" | "request_changes" | "comment",
     "findings": [
       {
         "file": "<path as it appears in the diff>",
         "line": <integer line number in the new file, or null for file-level comments>,
         "severity": "blocker" | "major" | "minor" | "nit",
         "message": "<one to three sentences explaining the issue>",
         "suggestion": "<optional concrete code change, or omit the field entirely>"
       }
     ]
   }
3. Severity meanings:
   - "blocker": must-fix; merging would introduce a defect, vulnerability, or data loss.
   - "major": should-fix; correctness, performance, or maintainability issue with real impact.
   - "minor": nice-to-fix; readability or low-impact concerns.
   - "nit": stylistic preference; not actionable.
3a. Blocker tier (mandatory). Findings that describe any of the following MUST use severity "blocker": hardcoded credentials or API keys; SQL injection (any user input concatenated into a SQL string); eval()/exec()/compile() of user-controlled input; deserialisation of untrusted data; remote-code-execution vectors; arbitrary-shell-command execution. Do not downgrade these to "major".
4. Verdict rules:
   - If any finding is "blocker" or "major", verdict is "request_changes".
   - Otherwise, if there is at least one finding, verdict is "comment".
   - If there are no findings, verdict is "approve".
5. Base every finding on a real change in the diff. Do not invent bugs that are not visible.
5a. Line-number anchor. The "line" field in every finding MUST refer to the new-file line number visible in the diff's `@@ -A,B +C,D @@` hunk headers, not to a position inside the diff text. If a hunk header reads `@@ -0,0 +1,71 @@`, then the first added line in that hunk is line 1 of the new file.
6. If the diff contains only binary changes or no reviewable text, return verdict "approve" and an empty findings array.

Example finding for a hardcoded credential:
{"verdict": "request_changes", "findings": [{"file": "samples/login_service.py", "line": 14, "severity": "blocker", "message": "ADMIN_API_KEY is hardcoded at module level. Anyone with read access to the source can extract it.", "suggestion": "ADMIN_API_KEY = os.environ['ADMIN_API_KEY']"}]}"""

USER_TEMPLATE = "Review the following unified diff:\n\n```diff\n{DIFF}\n```"


def _render_context_block(chunks: Iterable[_ChunkLike]) -> str:
    chunks_list = list(chunks)
    if not chunks_list:
        return ""
    total_tokens = sum(c.token_count for c in chunks_list)
    pieces = [
        f"Relevant context from repository (top-{len(chunks_list)} chunks, total {total_tokens} tokens):\n"
    ]
    for c in chunks_list:
        pieces.append(f"--- {c.file_path} (lines {c.start_line}-{c.end_line}) ---")
        pieces.append(c.content)
        pieces.append("")
    pieces.append("End of repository context.")
    pieces.append("")
    return "\n".join(pieces) + "\n"


def render_user_message(*, diff: str, retrieved_chunks: Iterable[_ChunkLike] | None = None) -> str:
    """Compose the USER message. Empty/missing chunks → byte-equivalent to v2."""
    block = _render_context_block(retrieved_chunks or [])
    if not block:
        return USER_TEMPLATE.format(DIFF=diff)
    return block + USER_TEMPLATE.format(DIFF=diff)


def build_messages(
    diff: str, *, retrieved_chunks: Iterable[_ChunkLike] | None = None
) -> list[ChatMessage]:
    return [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": render_user_message(diff=diff, retrieved_chunks=retrieved_chunks),
        },
    ]
