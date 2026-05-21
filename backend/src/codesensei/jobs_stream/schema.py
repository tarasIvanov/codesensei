"""Wire shapes for `WS /api/jobs/{job_id}/stream` frames (feature 013)."""

from __future__ import annotations

from typing import Literal, TypedDict

JobState = Literal["queued", "running", "success", "failed", "cancelled"]


class InitFrame(TypedDict, total=False):
    kind: Literal["init"]
    state: JobState
    files_total: int | None
    files_done: int
    chunks_done: int
    started_at: str | None
    eta_seconds: int | None


class ProgressFrame(TypedDict, total=False):
    kind: Literal["progress"]
    files_done: int
    files_total: int | None
    chunks_done: int
    current_file: str | None


class CompleteFrame(TypedDict, total=False):
    kind: Literal["complete"]
    state: Literal["success", "failed", "cancelled"]
    error_category: str | None
    error_message: str | None
    final_files: int
    final_chunks: int
