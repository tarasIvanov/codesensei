"""SQLAlchemy mapped classes for `review_runs` and `review_findings` (feature 009)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TIMESTAMP

from codesensei.settings_store.models import Base

__all__ = ["ReviewRun", "ReviewFinding"]


class ReviewRun(Base):
    __tablename__ = "review_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    input_kind: Mapped[str] = mapped_column(
        Text,
        CheckConstraint("input_kind IN ('diff','pr_url')", name="review_runs_input_kind_check"),
        nullable=False,
    )
    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    repo_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="SET NULL"),
        nullable=True,
    )
    diff: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(
        Text,
        CheckConstraint(
            "verdict IN ('approve','request_changes','comment')",
            name="review_runs_verdict_check",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    has_temporal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    context_files: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    findings: Mapped[list[ReviewFinding]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReviewFinding.position",
    )


class ReviewFinding(Base):
    __tablename__ = "review_findings"
    __table_args__ = (
        UniqueConstraint("run_id", "position", name="review_findings_run_position_uniq"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("review_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    file: Mapped[str] = mapped_column(Text, nullable=False)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(
        Text,
        CheckConstraint(
            "severity IN ('blocker','major','minor','nit')",
            name="review_findings_severity_check",
        ),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_context: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    run: Mapped[ReviewRun] = relationship(back_populates="findings")
