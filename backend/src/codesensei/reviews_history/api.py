"""FastAPI router for the review-history endpoints (feature 009)."""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import Response

from codesensei.db import get_sessionmaker
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.schema import Finding, TemporalEntry
from codesensei.reviews_history import store
from codesensei.reviews_history.models import ReviewRun
from codesensei.reviews_history.schema import (
    ReviewRunDetail,
    ReviewRunListResponse,
    ReviewRunSummary,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])
_logger = structlog.get_logger(__name__)


def _row_to_summary(row: ReviewRun) -> ReviewRunSummary:
    return ReviewRunSummary(
        id=row.id,
        created_at=row.created_at,
        input_kind=row.input_kind,  # type: ignore[arg-type]
        pr_url=row.pr_url,
        verdict=row.verdict,  # type: ignore[arg-type]
        provider=row.provider,
        elapsed_ms=row.elapsed_ms,
        finding_count=row.finding_count,
        has_temporal=row.has_temporal,
    )


def _row_to_finding(row: ReviewRun) -> list[Finding]:
    out: list[Finding] = []
    for f in sorted(row.findings, key=lambda x: x.position):
        temporal = None
        if f.temporal_context:
            temporal = [TemporalEntry(**entry) for entry in f.temporal_context]
        out.append(
            Finding(
                file=f.file,
                line=f.line,
                severity=f.severity,  # type: ignore[arg-type]
                message=f.message,
                suggestion=f.suggestion,
                temporal_context=temporal,
            )
        )
    return out


def _row_to_detail(row: ReviewRun) -> ReviewRunDetail:
    return ReviewRunDetail(
        id=row.id,
        created_at=row.created_at,
        input_kind=row.input_kind,  # type: ignore[arg-type]
        pr_url=row.pr_url,
        diff=row.diff,
        verdict=row.verdict,  # type: ignore[arg-type]
        provider=row.provider,
        elapsed_ms=row.elapsed_ms,
        findings=_row_to_finding(row),
        context_files=row.context_files,
    )


@router.get("", response_model=ReviewRunListResponse)
async def list_reviews(limit: int = Query(default=50, ge=1, le=200)) -> ReviewRunListResponse:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = await store.list_runs(session, limit=limit)
    return ReviewRunListResponse(runs=[_row_to_summary(r) for r in rows])


@router.get("/{run_id}", response_model=ReviewRunDetail)
async def get_review(run_id: UUID) -> ReviewRunDetail:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await store.fetch_run(session, run_id)
    if row is None:
        raise ReviewError(ReviewErrorCategory.INVALID_INPUT, "Review run not found.")
    return _row_to_detail(row)


@router.delete("/{run_id}", status_code=204)
async def delete_review(run_id: UUID) -> Response:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        deleted = await store.delete_run(session, run_id)
    if not deleted:
        raise ReviewError(ReviewErrorCategory.INVALID_INPUT, "Review run not found.")
    return Response(status_code=204)
