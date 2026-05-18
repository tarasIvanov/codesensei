"""Atomic chunk replacement + repo CRUD helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from codesensei.indexing.models import CodeChunk, Repo


@dataclass(frozen=True)
class ChunkInsert:
    """In-memory shape for a chunk-to-be-written. Mirrors `code_chunks` columns."""

    file_path: str
    language: str
    start_line: int
    end_line: int
    content: str
    token_count: int
    embedding: list[float]


async def upsert_repo(
    session: AsyncSession,
    *,
    source: str,
    source_kind: str,
    default_branch: str | None,
) -> tuple[Repo, bool]:
    """Insert-or-fetch a `repos` row. Returns (row, created_flag).

    The UNIQUE(source) constraint lets us upsert idempotently — a second POST for the
    same source hits the same row.
    """
    stmt = pg_insert(Repo).values(
        source=source, source_kind=source_kind, default_branch=default_branch
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=["source"]).returning(Repo)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    created = row is not None
    if row is None:
        existing = await session.execute(select(Repo).where(Repo.source == source))
        row = existing.scalar_one()
    return row, created


async def fetch_repo(session: AsyncSession, repo_id: UUID) -> Repo | None:
    result = await session.execute(select(Repo).where(Repo.id == repo_id))
    return result.scalar_one_or_none()


async def list_repos_ordered(session: AsyncSession) -> list[Repo]:
    """`indexed_at DESC NULLS LAST, created_at DESC`."""
    result = await session.execute(
        select(Repo).order_by(
            Repo.indexed_at.desc().nullslast(),
            Repo.created_at.desc(),
        )
    )
    return list(result.scalars().all())


async def delete_repo_by_id(session: AsyncSession, repo_id: UUID) -> bool:
    """Cascade deletes chunks. Returns True if a row was removed."""
    result = await session.execute(delete(Repo).where(Repo.id == repo_id))
    return (result.rowcount or 0) > 0


async def write_repo_failure(session: AsyncSession, repo_id: UUID, message: str) -> None:
    """Stamp `last_error` on a repo row (used by both sync and async failure paths)."""
    await session.execute(update(Repo).where(Repo.id == repo_id).values(last_error=message))


async def replace_chunks(
    session: AsyncSession,
    *,
    repo_id: UUID,
    new_chunks: Sequence[ChunkInsert],
    embedding_provider: str,
    embedding_model: str,
    indexed_at: datetime,
) -> int:
    """Atomic T2 swap: delete old chunks, insert new ones, refresh repo metadata.

    Implementation detail: we INSERT first (gather their ids), then DELETE WHERE id NOT IN (…)
    inside the same transaction. The whole call runs in a single transaction owned by the
    caller — `session.commit()` is **not** issued here; the caller decides commit boundary.
    """
    if new_chunks:
        rows_to_insert = [
            {
                "repo_id": repo_id,
                "file_path": c.file_path,
                "language": c.language,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "content": c.content,
                "token_count": c.token_count,
                "embedding": c.embedding,
            }
            for c in new_chunks
        ]
        result = await session.execute(
            CodeChunk.__table__.insert().returning(CodeChunk.id),
            rows_to_insert,
        )
        new_ids = [row[0] for row in result.fetchall()]
    else:
        new_ids = []

    # Delete the complement (rows for this repo that aren't in the new set).
    if new_ids:
        await session.execute(
            text("DELETE FROM code_chunks WHERE repo_id = :repo_id AND id <> ALL(:ids)"),
            {"repo_id": repo_id, "ids": new_ids},
        )
    else:
        await session.execute(delete(CodeChunk).where(CodeChunk.repo_id == repo_id))

    await session.execute(
        update(Repo)
        .where(Repo.id == repo_id)
        .values(
            indexed_at=indexed_at,
            chunk_count=len(new_chunks),
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            last_error=None,
        )
    )
    return len(new_chunks)


__all__ = [
    "ChunkInsert",
    "upsert_repo",
    "fetch_repo",
    "list_repos_ordered",
    "delete_repo_by_id",
    "write_repo_failure",
    "replace_chunks",
]
