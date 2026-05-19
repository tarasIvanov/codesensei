"""Async CRUD + LRU prune for review_runs / review_findings (feature 009)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from codesensei.review.schema import Finding
from codesensei.reviews_history.models import ReviewFinding, ReviewRun

# Module-private constants (FR-017, R6, R8 — not env-exposed in v1).
_HISTORY_MAX_ROWS = 1000
_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 200


def _temporal_to_jsonb(value: object) -> list[dict[str, Any]] | None:
    """Serialise a `temporal_context` field (pydantic list, dataclass list, or None) for JSONB."""
    if value is None:
        return None
    items = list(value)  # type: ignore[arg-type]
    if not items:
        return None
    out: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "model_dump"):
            out.append(item.model_dump())
        elif is_dataclass(item) and not isinstance(item, type):
            out.append(asdict(item))
        elif isinstance(item, dict):
            out.append(item)
        else:
            # Fallback — best effort
            out.append(dict(item))  # type: ignore[arg-type]
    return out


async def insert_run(
    session: AsyncSession,
    *,
    input_kind: str,
    pr_url: str | None,
    repo_id: UUID | None,
    diff: str,
    verdict: str,
    provider: str,
    elapsed_ms: int,
    findings: Sequence[Finding],
    context_files: list[str] | None,
) -> ReviewRun:
    """Insert a `review_runs` row + N `review_findings` rows. Commits before returning."""
    has_temporal = any(f.temporal_context for f in findings)
    run = ReviewRun(
        input_kind=input_kind,
        pr_url=pr_url,
        repo_id=repo_id,
        diff=diff,
        verdict=verdict,
        provider=provider,
        elapsed_ms=elapsed_ms,
        finding_count=len(findings),
        has_temporal=has_temporal,
        context_files=context_files,
    )
    for position, f in enumerate(findings):
        run.findings.append(
            ReviewFinding(
                position=position,
                file=f.file,
                line=f.line,
                severity=str(f.severity),
                message=f.message,
                suggestion=f.suggestion,
                temporal_context=_temporal_to_jsonb(f.temporal_context),
            )
        )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def list_runs(session: AsyncSession, *, limit: int = _DEFAULT_LIST_LIMIT) -> list[ReviewRun]:
    """Return the N most-recent runs, newest first."""
    n = limit
    if n < 1:
        n = _DEFAULT_LIST_LIMIT
    if n > _MAX_LIST_LIMIT:
        n = _MAX_LIST_LIMIT
    stmt = select(ReviewRun).order_by(ReviewRun.created_at.desc(), ReviewRun.id.desc()).limit(n)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def fetch_run(session: AsyncSession, run_id: UUID) -> ReviewRun | None:
    """Return a single run with its findings eager-loaded ordered by position."""
    stmt = select(ReviewRun).where(ReviewRun.id == run_id).options(selectinload(ReviewRun.findings))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_run(session: AsyncSession, run_id: UUID) -> bool:
    """Delete a run and its findings (CASCADE). Returns True if a row was removed."""
    result = await session.execute(delete(ReviewRun).where(ReviewRun.id == run_id))
    deleted = (result.rowcount or 0) > 0
    if deleted:
        await session.commit()
    return deleted


async def prune_to_cap(session: AsyncSession) -> int:
    """Enforce `_HISTORY_MAX_ROWS` via mtime LRU. Returns the number of rows deleted."""
    count_stmt = select(func.count(ReviewRun.id))
    count = (await session.execute(count_stmt)).scalar_one()
    overflow = max(0, int(count) - _HISTORY_MAX_ROWS)
    if overflow == 0:
        return 0
    # Inner SELECT picks the OLDEST `overflow` rows; outer DELETE removes them.
    inner = select(ReviewRun.id).order_by(ReviewRun.created_at.asc()).limit(overflow)
    result = await session.execute(delete(ReviewRun).where(ReviewRun.id.in_(inner)))
    await session.commit()
    return result.rowcount or 0


__all__ = [
    "insert_run",
    "list_runs",
    "fetch_run",
    "delete_run",
    "prune_to_cap",
]
