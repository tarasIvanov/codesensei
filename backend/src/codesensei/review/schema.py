"""Wire-shape pydantic models for POST /api/review (per data-model.md)."""

from __future__ import annotations

import re
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from codesensei.review.errors import ReviewError, ReviewErrorCategory

_MAX_MESSAGE_CHARS = 2000
_MAX_SUGGESTION_CHARS = 4000
_PR_URL_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/pull/\d+$")
_DIFF_HEADER_GIT = re.compile(r"^diff --git ", re.MULTILINE)
_DIFF_HEADER_MINUS = re.compile(r"^--- a/", re.MULTILINE)
_DIFF_HEADER_PLUS = re.compile(r"^\+\+\+ b/", re.MULTILINE)


def looks_like_unified_diff(text: str) -> bool:
    if not text:
        return False
    if _DIFF_HEADER_GIT.search(text):
        return True
    return bool(_DIFF_HEADER_MINUS.search(text) and _DIFF_HEADER_PLUS.search(text))


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


class Severity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    NIT = "nit"


class Verdict(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    COMMENT = "comment"


class TemporalEntry(BaseModel):
    """One commit that touched a specific line window in a file (feature 008)."""

    model_config = ConfigDict(extra="ignore")

    commit_sha: str = Field(min_length=40, max_length=40)
    short_sha: str = Field(min_length=7, max_length=7)
    author_email: str = Field(min_length=1, max_length=254)
    author_date: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    hunk_lines_changed: int = Field(ge=0)

    @field_validator("subject")
    @classmethod
    def _truncate_subject(cls, v: str) -> str:
        return _truncate(v, 120)


class Finding(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=False)

    file: str = Field(min_length=1)
    line: int | None = None
    severity: Severity
    message: str = Field(min_length=1)
    suggestion: str | None = None
    temporal_context: list[TemporalEntry] | None = None

    @field_validator("severity", mode="before")
    @classmethod
    def _normalise_severity(cls, v: object) -> object:
        # LLMs occasionally emit "Major", "MAJOR", " minor ", etc.
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("line", mode="before")
    @classmethod
    def _coerce_line(cls, v: object) -> object:
        # LLMs sometimes emit 0 for "file-level" and string digits like "12".
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped or stripped.lower() in {"null", "none", "n/a"}:
                return None
            try:
                v = int(stripped)
            except ValueError:
                return v  # let the int validator fail loudly
        if isinstance(v, int) and v <= 0:
            return None
        return v

    @field_validator("message")
    @classmethod
    def _truncate_message(cls, v: str) -> str:
        return _truncate(v, _MAX_MESSAGE_CHARS)

    @field_validator("suggestion")
    @classmethod
    def _truncate_suggestion(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _truncate(v, _MAX_SUGGESTION_CHARS)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdict: Verdict
    findings: list[Finding]
    provider: str
    elapsed_ms: int
    context_files: list[str] | None = None  # NEW (feature 005): present only when repo_id was used


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diff: str | None = None
    pr_url: str | None = None
    repo_id: UUID | None = None  # NEW (feature 005): opt-in RAG augmentation

    @model_validator(mode="after")
    def _exactly_one(self) -> ReviewRequest:
        has_diff = self.diff is not None and self.diff != ""
        has_url = self.pr_url is not None and self.pr_url != ""
        if has_diff and has_url:
            raise ReviewError(
                ReviewErrorCategory.INVALID_INPUT,
                "Provide either `diff` or `pr_url`, not both.",
            )
        if not has_diff and not has_url:
            raise ReviewError(
                ReviewErrorCategory.INVALID_INPUT,
                "Provide either a unified diff or a GitHub PR URL.",
            )
        if has_diff and not looks_like_unified_diff(self.diff or ""):
            raise ReviewError(
                ReviewErrorCategory.INVALID_INPUT,
                "The pasted text does not look like a unified diff.",
            )
        if has_url and not _PR_URL_RE.match(self.pr_url or ""):
            raise ReviewError(
                ReviewErrorCategory.INVALID_INPUT,
                "PR URL must match https://github.com/<owner>/<repo>/pull/<n>.",
            )
        return self
