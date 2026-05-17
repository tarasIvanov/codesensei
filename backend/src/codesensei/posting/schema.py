"""Pydantic wire models for POST /api/review/post."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from codesensei.review.schema import ReviewResult


class PostReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_result: ReviewResult
    pr_url: str = Field(min_length=1)
    event: Literal["COMMENT", "REQUEST_CHANGES", "APPROVE"]


class PostedReviewReceipt(BaseModel):
    model_config = ConfigDict(extra="ignore")

    review_id: int
    html_url: str
    posted_at: datetime
    comment_count: int
    attempted_calls: int
