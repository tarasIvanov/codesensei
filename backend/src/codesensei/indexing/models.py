"""SQLAlchemy mapped classes for `repos` and `code_chunks` (feature 005)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TIMESTAMP

from codesensei.settings_store.models import Base

__all__ = ["Repo", "CodeChunk", "Base"]


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_kind: Mapped[str] = mapped_column(
        Text,
        CheckConstraint("source_kind IN ('https','local')", name="repos_source_kind_check"),
        nullable=False,
    )
    default_branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    chunks: Mapped[list[CodeChunk]] = relationship(
        back_populates="repo",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    repo_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("start_line >= 1", name="code_chunks_start_line_check"),
        nullable=False,
    )
    end_line: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("end_line >= start_line", name="code_chunks_end_line_check"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("token_count >= 0", name="code_chunks_token_count_check"),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)

    repo: Mapped[Repo] = relationship(back_populates="chunks")

    __table_args__ = (Index("code_chunks_repo_id_idx", "repo_id"),)
