"""Pydantic wire shapes for the review-history endpoints (feature 009)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from codesensei.review.schema import Finding


class ReviewRunSummary(BaseModel):
    """One row in `GET /api/reviews`."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    created_at: datetime
    input_kind: Literal["diff", "pr_url"]
    pr_url: str | None = None
    verdict: Literal["approve", "request_changes", "comment"]
    provider: str
    elapsed_ms: int
    finding_count: int
    has_temporal: bool


class ReviewRunListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    runs: list[ReviewRunSummary]


class ReviewRunDetail(BaseModel):
    """Response of `GET /api/reviews/{run_id}` — re-uses `Finding` from feature 003/008."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    created_at: datetime
    input_kind: Literal["diff", "pr_url"]
    pr_url: str | None = None
    diff: str
    verdict: Literal["approve", "request_changes", "comment"]
    provider: str
    elapsed_ms: int
    findings: list[Finding]
    context_files: list[str] | None = None
