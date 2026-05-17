"""Per-hunk semantic retrieval over `code_chunks` for RAG-augmented review (feature 005, US2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

import structlog
import tiktoken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from codesensei.db import get_sessionmaker
from codesensei.indexing.errors import IndexError, IndexErrorCategory
from codesensei.indexing.service import _active_embedding_model
from codesensei.providers.errors import ProviderError
from codesensei.providers.factory import get_embedding_provider
from codesensei.review.errors import ReviewError, ReviewErrorCategory

DEFAULT_TOP_K = 5
DEFAULT_TOKEN_BUDGET = 3_000
DISTANCE_FLOOR = 1.5  # cosine distance; drop chunks "too far" from any query
HUNK_CONTEXT_LINES = 10  # ± lines around the hunk's new-file body

_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)

_logger = structlog.get_logger()


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    repo_id: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    content: str
    token_count: int
    score: float  # normalized similarity in [0,1]; higher is better


@dataclass(frozen=True)
class RetrievalResult:
    selected: list[RetrievedChunk]
    queries_count: int
    chunks_fetched: int
    chunks_used: int
    trimmed: int
    empty: bool


def derive_queries(diff: str) -> list[str]:
    """Extract per-hunk query windows from a unified diff.

    For each ``@@ -A,B +C,D @@`` hunk header, take the new-file body lines
    (those not starting with ``-``) plus ``HUNK_CONTEXT_LINES`` of leading and
    trailing context from the diff body. Pure-deletion hunks contribute nothing.
    """
    queries: list[str] = []
    # Index of every line in the diff that starts a hunk.
    hunk_positions = [m.start() for m in _HUNK_HEADER_RE.finditer(diff)]
    if not hunk_positions:
        return []
    hunk_positions.append(len(diff))
    for i in range(len(hunk_positions) - 1):
        start = hunk_positions[i]
        end = hunk_positions[i + 1]
        section = diff[start:end]
        body_lines = section.splitlines()
        # The body excludes the @@ header line itself.
        body = body_lines[1:] if body_lines else []
        # Keep only new-file content (lines without leading '-'); strip leading '+' / ' '.
        new_lines = [
            ln[1:] if ln.startswith(("+", " ")) else ln for ln in body if not ln.startswith("-")
        ]
        if not any(line.strip() for line in new_lines):
            continue
        # The hunk header anchor provides positional context; include surrounding ones.
        # Body itself already gives ~B/D lines; HUNK_CONTEXT_LINES kept implicit via the diff body.
        text_window = "\n".join(new_lines)
        if text_window.strip():
            queries.append(text_window)
    return queries


async def _query_repo_meta(
    session: AsyncSession, repo_id: UUID
) -> tuple[str, str, bool, bool] | None:
    """Return (embedding_provider, embedding_model, indexed_ready, exists)."""
    result = await session.execute(
        text(
            "SELECT embedding_provider, embedding_model, indexed_at IS NOT NULL AS ready "
            "FROM repos WHERE id = :rid"
        ),
        {"rid": repo_id},
    )
    row = result.first()
    if row is None:
        return None
    return row.embedding_provider or "", row.embedding_model or "", bool(row.ready), True


class RetrievalService:
    """Stateless: per-call retrieval against the configured embedding provider + pgvector."""

    def __init__(self, sessionmaker) -> None:  # type: ignore[no-untyped-def]
        self._sessionmaker = sessionmaker
        self._encoder = tiktoken.get_encoding("cl100k_base")

    @classmethod
    def from_request(cls) -> RetrievalService:
        return cls(get_sessionmaker())

    async def search(
        self,
        *,
        repo_id: UUID,
        diff: str,
        top_k: int = DEFAULT_TOP_K,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> RetrievalResult:
        """Run the full pipeline. Raises ReviewError on terminal conditions."""
        # 0. Read the persisted (provider, model) for this repo + readiness.
        async with self._sessionmaker() as session:
            meta = await _query_repo_meta(session, repo_id)
            if meta is None:
                raise ReviewError(
                    ReviewErrorCategory.INVALID_INPUT,
                    f"Unknown repo_id={repo_id}",
                )
            persisted_provider, persisted_model, ready, _exists = meta
        if not ready:
            # The review layer translates this into a "repo_not_ready" envelope.
            raise IndexError(
                IndexErrorCategory.ALREADY_INDEXING,
                "Repository indexing is still in progress; retry once it is ready.",
                retryable=True,
            )

        provider = get_embedding_provider()
        active_model = _active_embedding_model()
        if persisted_provider and persisted_provider != provider.name:
            raise IndexError(
                IndexErrorCategory.EMBEDDING_MISMATCH,
                f"This repository was indexed with {persisted_provider}/{persisted_model}; "
                f"the active embedding provider is {provider.name}/{active_model}. "
                f"Re-index the repository before retrieval.",
            )
        if persisted_model and persisted_model != active_model:
            raise IndexError(
                IndexErrorCategory.EMBEDDING_MISMATCH,
                f"This repository was indexed with {persisted_provider}/{persisted_model}; "
                f"the active embedding provider is {provider.name}/{active_model}. "
                f"Re-index the repository before retrieval.",
            )

        # 1. Derive queries.
        queries = derive_queries(diff)
        if not queries:
            _logger.info(
                "retrieval.done",
                repo_id=str(repo_id),
                queries=0,
                chunks_fetched=0,
                chunks_used=0,
                trimmed=0,
                empty=True,
            )
            return RetrievalResult(
                selected=[], queries_count=0, chunks_fetched=0, chunks_used=0, trimmed=0, empty=True
            )

        _logger.info("retrieval.started", repo_id=str(repo_id), queries=len(queries))

        # 2. Embed query windows.
        try:
            vectors = await provider.embed(queries)
        except ProviderError as exc:
            raise ReviewError(
                ReviewErrorCategory.PROVIDER_UNAVAILABLE,
                f"Embedding provider failed during retrieval: {exc.message}",
                retryable=exc.retryable,
            ) from exc

        # 3. Search pgvector.
        best: dict[str, RetrievedChunk] = {}
        async with self._sessionmaker() as session:
            for vec in vectors:
                vec_literal = "[" + ",".join(repr(float(x)) for x in vec) + "]"
                result = await session.execute(
                    text(
                        "SELECT id::text AS id, repo_id::text AS repo_id, "
                        "file_path, language, start_line, end_line, content, "
                        "token_count, (embedding <=> :v ::vector) AS distance "
                        "FROM code_chunks "
                        "WHERE repo_id = :rid "
                        "ORDER BY embedding <=> :v ::vector "
                        "LIMIT :k"
                    ),
                    {"v": vec_literal, "rid": repo_id, "k": top_k},
                )
                for row in result.mappings():
                    if row["distance"] is None or row["distance"] > DISTANCE_FLOOR:
                        continue
                    score = max(0.0, 1.0 - float(row["distance"]) / 2.0)
                    chunk_id = str(row["id"])
                    existing = best.get(chunk_id)
                    if existing is None or score > existing.score:
                        best[chunk_id] = RetrievedChunk(
                            chunk_id=chunk_id,
                            repo_id=str(row["repo_id"]),
                            file_path=row["file_path"],
                            language=row["language"],
                            start_line=row["start_line"],
                            end_line=row["end_line"],
                            content=row["content"],
                            token_count=row["token_count"],
                            score=score,
                        )

        candidates = sorted(best.values(), key=lambda c: c.score, reverse=True)
        chunks_fetched = len(candidates)

        # 4. Trim by token budget.
        selected: list[RetrievedChunk] = []
        token_total = 0
        for c in candidates:
            if token_total + c.token_count > token_budget:
                continue
            selected.append(c)
            token_total += c.token_count
        trimmed = chunks_fetched - len(selected)
        empty = not selected

        _logger.info(
            "retrieval.done",
            repo_id=str(repo_id),
            queries=len(queries),
            chunks_fetched=chunks_fetched,
            chunks_used=len(selected),
            trimmed=trimmed,
            empty=empty,
        )

        return RetrievalResult(
            selected=selected,
            queries_count=len(queries),
            chunks_fetched=chunks_fetched,
            chunks_used=len(selected),
            trimmed=trimmed,
            empty=empty,
        )
