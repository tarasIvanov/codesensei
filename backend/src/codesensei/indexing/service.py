"""Indexing orchestrator: clone → chunk → embed → atomic store."""
from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import structlog
import tiktoken
from redis.exceptions import RedisError

from codesensei.config import get_settings
from codesensei.db import get_sessionmaker
from codesensei.indexing.chunker import (
    chunk_repo,
    count_source_files,
)
from codesensei.indexing.clone import materialise, normalise_source
from codesensei.indexing.errors import IndexError, IndexErrorCategory
from codesensei.indexing.models import Repo
from codesensei.indexing.store import (
    ChunkInsert,
    delete_repo_by_id,
    fetch_repo,
    list_repos_ordered,
    replace_chunks,
    upsert_repo,
    write_repo_failure,
)
from codesensei.providers.errors import ProviderError
from codesensei.providers.factory import get_embedding_provider

MAX_CHUNKS_PER_REPO = 5_000
SYNC_FILE_THRESHOLD = 200
EMBED_BATCH_SIZE = 100
EXPECTED_EMBEDDING_DIM = 1536

_logger = structlog.get_logger()


def _tiktoken_encoder():
    """Single shared encoder; `cl100k_base` is OpenAI's default for `text-embedding-3-small`."""
    return tiktoken.get_encoding("cl100k_base")


def _active_embedding_model() -> str:
    """Resolve the model the active EmbeddingProvider will use, honouring settings overrides."""
    settings = get_settings()
    if settings.embedding_model:
        return settings.embedding_model
    if settings.embedding_provider == "ollama":
        return "nomic-embed-text"
    return "text-embedding-3-small"


def _repo_status(repo: Repo) -> Literal["ready", "indexing", "failed"]:
    if repo.indexed_at is not None:
        return "ready"
    if repo.last_error is not None:
        return "failed"
    return "indexing"


def _serialise_repo(repo: Repo) -> dict[str, object]:
    return {
        "repo_id": str(repo.id),
        "source": repo.source,
        "source_kind": repo.source_kind,
        "default_branch": repo.default_branch,
        "indexed_at": repo.indexed_at.isoformat() if repo.indexed_at else None,
        "chunk_count": repo.chunk_count,
        "embedding_provider": repo.embedding_provider,
        "embedding_model": repo.embedding_model,
        "status": _repo_status(repo),
        "last_error": repo.last_error,
    }


class IndexingService:
    """Stateless orchestrator. Re-instantiated per request so settings updates are picked up."""

    def __init__(self, sessionmaker) -> None:  # type: ignore[no-untyped-def]
        self._sessionmaker = sessionmaker
        self._encoder = _tiktoken_encoder()

    @classmethod
    def from_request(cls) -> IndexingService:
        return cls(get_sessionmaker())

    # ------- HTTP-facing entry points -------

    async def dispatch(
        self, *, source: str, default_branch: str | None
    ) -> dict[str, object]:
        """Decide sync vs async based on the pre-scan; deferred-import to keep enqueue optional."""
        canonical, source_kind = normalise_source(source)
        # Pre-scan: need to materialise the working tree exactly once. For sync we'll re-use it.
        async with materialise(canonical, source_kind, default_branch) as root:
            file_count = count_source_files(root)
            if file_count <= SYNC_FILE_THRESHOLD:
                snapshot = await self._run_sync_within_tree(
                    source=canonical,
                    source_kind=source_kind,
                    default_branch=default_branch,
                    root=root,
                )
                return {
                    "repo_id": str(snapshot["repo_id"]),
                    "chunk_count": snapshot["chunk_count"],
                    "indexed_at": snapshot["indexed_at"],
                    "mode": "sync",
                }
        # async path: tree dropped after the pre-scan; the worker re-clones.
        repo_id = await self._register_async(
            source=canonical, source_kind=source_kind, default_branch=default_branch
        )
        try:
            from codesensei.tasks.enqueue import enqueue_index_repo

            job_id = await enqueue_index_repo(
                repo_id=repo_id,
                source=canonical,
                source_kind=source_kind,
                default_branch=default_branch,
            )
        except (ImportError, RedisError, OSError) as exc:
            # Roll back the row we just inserted (it would be useless without a job).
            await self._delete_if_pristine(repo_id)
            raise IndexError(
                IndexErrorCategory.QUEUE_UNAVAILABLE,
                f"Job queue is unreachable: {exc}",
                retryable=True,
            ) from exc
        return {"repo_id": str(repo_id), "job_id": job_id, "mode": "async"}

    async def list_repos(self) -> list[dict[str, object]]:
        async with self._sessionmaker() as session:
            rows = await list_repos_ordered(session)
        return [_serialise_repo(r) for r in rows]

    async def delete_repo(self, repo_id: UUID) -> None:
        async with self._sessionmaker() as session:
            row = await fetch_repo(session, repo_id)
            if row is None:
                raise IndexError(IndexErrorCategory.NOT_FOUND, f"No repo with id={repo_id}")
            if row.indexed_at is None and row.last_error is None:
                raise IndexError(
                    IndexErrorCategory.DELETE_DURING_INDEX,
                    "Cannot delete while indexing is in progress.",
                    retryable=True,
                )
            removed = await delete_repo_by_id(session, repo_id)
            await session.commit()
            if not removed:
                raise IndexError(IndexErrorCategory.NOT_FOUND, f"No repo with id={repo_id}")

    # ------- Async-worker entry point -------

    async def run_for_existing_repo(self, repo_id: UUID) -> dict[str, object]:
        """Called from the arq worker. Re-clones the source and fills the row."""
        async with self._sessionmaker() as session:
            row = await fetch_repo(session, repo_id)
            if row is None:
                raise IndexError(IndexErrorCategory.NOT_FOUND, f"No repo with id={repo_id}")
            source = row.source
            source_kind = row.source_kind
            default_branch = row.default_branch
        try:
            async with materialise(source, source_kind, default_branch) as root:  # type: ignore[arg-type]
                snapshot = await self._fill_repo(
                    repo_id=repo_id,
                    root=root,
                    source=source,
                    delete_on_failure=False,
                )
            return {
                "repo_id": str(repo_id),
                "chunk_count": snapshot["chunk_count"],
                "indexed_at": snapshot["indexed_at"],
                "embedding_provider": snapshot["embedding_provider"],
                "embedding_model": snapshot["embedding_model"],
            }
        except IndexError as exc:
            await self._record_failure(repo_id, exc.message)
            raise

    # ------- Internal helpers -------

    async def _register_async(
        self,
        *,
        source: str,
        source_kind: Literal["https", "local"],
        default_branch: str | None,
    ) -> UUID:
        async with self._sessionmaker() as session:
            row, created = await upsert_repo(
                session,
                source=source,
                source_kind=source_kind,
                default_branch=default_branch,
            )
            if not created and row.indexed_at is None and row.last_error is None:
                # An async pass is already in flight for this source.
                await session.commit()
                raise IndexError(
                    IndexErrorCategory.ALREADY_INDEXING,
                    f"Indexing already in progress for source={source!r}",
                    retryable=True,
                )
            # Mark as pending (clear any prior last_error so the UI doesn't show stale failure).
            row.indexed_at = None
            row.last_error = None
            row.chunk_count = 0
            await session.commit()
            return row.id

    async def _delete_if_pristine(self, repo_id: UUID) -> None:
        """Drop the row only if it has no chunks and no successful pass — i.e. we created it."""
        async with self._sessionmaker() as session:
            row = await fetch_repo(session, repo_id)
            if row and row.indexed_at is None and row.chunk_count == 0:
                await delete_repo_by_id(session, repo_id)
                await session.commit()

    async def _record_failure(self, repo_id: UUID, message: str) -> None:
        async with self._sessionmaker() as session:
            await write_repo_failure(session, repo_id, message)
            await session.commit()

    async def _run_sync_within_tree(
        self,
        *,
        source: str,
        source_kind: Literal["https", "local"],
        default_branch: str | None,
        root: Path,
    ) -> dict[str, Any]:
        created_now = False
        async with self._sessionmaker() as session:
            row, created_now = await upsert_repo(
                session,
                source=source,
                source_kind=source_kind,
                default_branch=default_branch,
            )
            if not created_now and row.indexed_at is None and row.last_error is None:
                # An async indexing is in flight — refuse a parallel sync overwrite.
                await session.commit()
                raise IndexError(
                    IndexErrorCategory.ALREADY_INDEXING,
                    f"Indexing already in progress for source={source!r}",
                    retryable=True,
                )
            repo_id = row.id
            await session.commit()

        try:
            return await self._fill_repo(
                repo_id=repo_id,
                root=root,
                source=source,
                delete_on_failure=created_now,
            )
        except IndexError as exc:
            if created_now:
                # Roll back the row we created in this same request to avoid a tombstone.
                await self._record_failure(repo_id, exc.message)
                await self._delete_if_pristine(repo_id)
            else:
                await self._record_failure(repo_id, exc.message)
            raise

    async def _fill_repo(
        self,
        *,
        repo_id: UUID,
        root: Path,
        source: str,
        delete_on_failure: bool,  # noqa: ARG002 — caller handles deletion; here for parity
    ) -> dict[str, Any]:
        started = time.perf_counter()
        chunks = await chunk_repo(root)
        if len(chunks) > MAX_CHUNKS_PER_REPO:
            raise IndexError(
                IndexErrorCategory.PAYLOAD_TOO_LARGE,
                f"Repository would produce {len(chunks)} chunks; the per-repo cap is "
                f"{MAX_CHUNKS_PER_REPO}.",
            )
        if not chunks:
            # Empty repo (binary-only or all skipped): record a successful 0-chunk pass.
            now = datetime.now(UTC)
            provider = get_embedding_provider()
            model = _active_embedding_model()
            async with self._sessionmaker() as session:
                await replace_chunks(
                    session,
                    repo_id=repo_id,
                    new_chunks=(),
                    embedding_provider=provider.name,
                    embedding_model=model,
                    indexed_at=now,
                )
                await session.commit()
            _logger.info(
                "indexing.complete",
                repo_id=str(repo_id),
                provider=provider.name,
                model=model,
                files_scanned=count_source_files(root),
                chunks=0,
                embedding_seconds=0.0,
                total_seconds=round(time.perf_counter() - started, 2),
            )
            return {
                "repo_id": repo_id,
                "chunk_count": 0,
                "indexed_at": now.isoformat(),
                "embedding_provider": provider.name,
                "embedding_model": model,
            }

        # Token counts (deterministic for budget math + invariant for indexing cost reports).
        for c in chunks:  # noqa: B007 — readability
            pass
        token_counts = [len(self._encoder.encode(c.content)) for c in chunks]

        # Embed in batches.
        try:
            provider = get_embedding_provider()
        except ProviderError as exc:
            raise IndexError(
                IndexErrorCategory.EMBEDDING_FAILED,
                f"Embedding provider not available: {exc.message}",
                retryable=False,
            ) from exc
        model = _active_embedding_model()

        embeddings: list[list[float]] = []
        embed_start = time.perf_counter()
        try:
            for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
                texts = [c.content for c in batch]
                vectors = await provider.embed(texts)
                if any(len(v) != EXPECTED_EMBEDDING_DIM for v in vectors):
                    raise IndexError(
                        IndexErrorCategory.EMBEDDING_DIMENSION_MISMATCH,
                        f"Embedding provider returned a vector with dim "
                        f"{len(vectors[0]) if vectors else 'unknown'}; "
                        f"expected {EXPECTED_EMBEDDING_DIM}.",
                    )
                embeddings.extend(vectors)
        except ProviderError as exc:
            raise IndexError(
                IndexErrorCategory.EMBEDDING_FAILED,
                f"Embedding provider failed: {exc.message}",
                retryable=exc.retryable,
            ) from exc
        embed_seconds = round(time.perf_counter() - embed_start, 2)

        # Persist atomically.
        now = datetime.now(UTC)
        inserts = [
            ChunkInsert(
                file_path=c.file_path,
                language=c.language,
                start_line=c.start_line,
                end_line=c.end_line,
                content=c.content,
                token_count=tc,
                embedding=emb,
            )
            for c, tc, emb in zip(chunks, token_counts, embeddings, strict=True)
        ]
        async with self._sessionmaker() as session:
            await replace_chunks(
                session,
                repo_id=repo_id,
                new_chunks=inserts,
                embedding_provider=provider.name,
                embedding_model=model,
                indexed_at=now,
            )
            await session.commit()

        files_scanned = len({c.file_path for c in chunks})
        _logger.info(
            "indexing.complete",
            repo_id=str(repo_id),
            provider=provider.name,
            model=model,
            files_scanned=files_scanned,
            chunks=len(chunks),
            embedding_seconds=embed_seconds,
            total_seconds=round(time.perf_counter() - started, 2),
            source=source,
        )
        return {
            "repo_id": repo_id,
            "chunk_count": len(chunks),
            "indexed_at": now.isoformat(),
            "embedding_provider": provider.name,
            "embedding_model": model,
        }
