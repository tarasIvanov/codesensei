"""ReviewService — orchestrates prompt → provider chat → strict parse → ReviewResult."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict
from uuid import UUID

import structlog

from codesensei.config import get_settings
from codesensei.db import get_sessionmaker
from codesensei.indexing import store as repos_store
from codesensei.indexing.errors import IndexError, IndexErrorCategory
from codesensei.indexing.retrieval import RetrievalResult, RetrievalService
from codesensei.providers import ProviderError, get_llm_provider
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.git_temporal import (
    FileTemporalPool,
    collapse_diff_to_windows,
    fetch_temporal_pool_for_review,
)
from codesensei.review.parser import parse_review
from codesensei.review.pricing import compute_cost_usd
from codesensei.review.prompt import build_messages
from codesensei.review.schema import Finding, ReviewResult, TemporalEntry
from codesensei.reviews_history import store as history_store

_logger = structlog.get_logger(__name__)

_HUNK_HEADER_RE = re.compile(r"^@@\s-\d+(?:,\d+)?\s\+(\d+)(?:,(\d+))?\s@@")
_FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$")


def _extract_rhs_hunks(diff: str) -> dict[str, list[tuple[int, int]]]:
    """Parse a unified diff into ``{file_path: [(start_line, length), ...]}``."""
    out: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None
    for raw in diff.splitlines():
        m_file = _FILE_HEADER_RE.match(raw)
        if m_file:
            current_file = m_file.group(1).strip()
            continue
        if current_file is None:
            continue
        m_hunk = _HUNK_HEADER_RE.match(raw)
        if not m_hunk:
            continue
        start = int(m_hunk.group(1))
        length = int(m_hunk.group(2)) if m_hunk.group(2) else 1
        if start <= 0 or length <= 0:
            continue
        out.setdefault(current_file, []).append((start, length))
    return out


async def _resolve_repo_source(repo_id: UUID) -> str | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        repo = await repos_store.fetch_repo(session, repo_id)
        if repo is None:
            return None
        return repo.source


def _attach_temporal_context(findings: list[Finding], pool: FileTemporalPool) -> None:
    """Route the in-memory pool back onto each finding via (file, line) match."""
    if not pool:
        return
    for finding in findings:
        if finding.line is None:
            continue
        windows = pool.get(finding.file)
        if not windows:
            continue
        for window, entries in windows:
            if window.start_line <= finding.line <= window.end_line and entries:
                finding.temporal_context = [TemporalEntry(**asdict(entry)) for entry in entries]
                break


def _enforce_size(diff: str) -> None:
    limit = get_settings().review_max_diff_bytes
    if len(diff.encode("utf-8")) > limit:
        raise ReviewError(
            ReviewErrorCategory.PAYLOAD_TOO_LARGE,
            f"Diff exceeds the {limit // 1000} KB limit. Try a smaller change.",
        )


async def _retrieve_context(repo_id: UUID, diff: str) -> RetrievalResult:
    """Run retrieval and translate IndexError → ReviewError envelopes."""
    service = RetrievalService.from_request()
    try:
        return await service.search(repo_id=repo_id, diff=diff)
    except IndexError as exc:
        if exc.category == IndexErrorCategory.EMBEDDING_MISMATCH:
            raise ReviewError(
                ReviewErrorCategory.EMBEDDING_MISMATCH,
                exc.message,
                retryable=False,
            ) from exc
        if exc.category == IndexErrorCategory.ALREADY_INDEXING:
            raise ReviewError(
                ReviewErrorCategory.REPO_NOT_READY,
                exc.message,
                retryable=exc.retryable,
            ) from exc
        if exc.category == IndexErrorCategory.NOT_FOUND:
            raise ReviewError(
                ReviewErrorCategory.INVALID_INPUT,
                exc.message,
                retryable=exc.retryable,
            ) from exc
        raise ReviewError(
            ReviewErrorCategory.INTERNAL,
            f"Retrieval failed: {exc.message}",
            retryable=exc.retryable,
        ) from exc


async def _persist_run(
    *,
    input_kind: str,
    pr_url: str | None,
    repo_id: UUID | None,
    diff: str,
    verdict: str,
    provider_name: str,
    elapsed_ms: int,
    findings: list[Finding],
    context_files: list[str] | None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost_usd: float | None = None,
) -> None:
    """Best-effort persist + LRU prune. Failure logs a warning and proceeds."""
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            run = await history_store.insert_run(
                session,
                input_kind=input_kind,
                pr_url=pr_url,
                repo_id=repo_id,
                diff=diff,
                verdict=verdict,
                provider=provider_name,
                elapsed_ms=elapsed_ms,
                findings=findings,
                context_files=context_files,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
            )
            pruned = await history_store.prune_to_cap(session)
        _logger.info(
            "review_persisted",
            run_id=str(run.id),
            finding_count=len(findings),
            pruned=pruned,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort: live response is canonical
        _logger.warning("review_persist_failed", reason=str(exc)[:200])


async def _run_chat(
    diff: str,
    *,
    repo_id: UUID | None = None,
    original_pr_url: str | None = None,
) -> ReviewResult:
    _enforce_size(diff)

    retrieved: RetrievalResult | None = None
    if repo_id is not None:
        retrieved = await _retrieve_context(repo_id, diff)

    temporal_pool: FileTemporalPool = {}
    if repo_id is not None:
        repo_source = await _resolve_repo_source(repo_id)
        if repo_source:
            hunks_by_file = _extract_rhs_hunks(diff)
            windows_by_file = collapse_diff_to_windows(hunks_by_file)
            if windows_by_file:
                temporal_pool, summary = await fetch_temporal_pool_for_review(
                    repo_id=repo_id,
                    repo_source=repo_source,
                    windows_by_file=windows_by_file,
                )
                _logger.info(
                    "temporal_fetch",
                    repo_id=str(repo_id),
                    files_count=summary.files_count,
                    entries_total=summary.entries_total,
                    elapsed_ms=summary.elapsed_ms,
                    budget_exceeded=summary.budget_exceeded,
                )

    provider = get_llm_provider()
    messages = build_messages(
        diff,
        retrieved_chunks=retrieved.selected if retrieved else None,
        temporal_pool=temporal_pool or None,
    )
    timeout = get_settings().review_llm_timeout_s
    started = time.perf_counter()
    try:
        raw = await asyncio.wait_for(
            provider.chat(messages, temperature=0.1, max_tokens=4096),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_UNAVAILABLE,
            "Review service timed out — try again.",
            retryable=True,
        ) from exc
    except ProviderError as exc:
        raise ReviewError(
            ReviewErrorCategory.PROVIDER_UNAVAILABLE,
            f"{exc.provider} provider error: {exc.message}",
            retryable=exc.retryable,
        ) from exc
    verdict, findings = parse_review(provider.name, raw)
    if temporal_pool:
        _attach_temporal_context(findings, temporal_pool)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    usage = getattr(provider, "_last_usage", None)
    prompt_tokens = usage.prompt_tokens if usage else None
    completion_tokens = usage.completion_tokens if usage else None
    cost_usd = compute_cost_usd(
        provider.name,
        usage.model if usage else None,
        prompt_tokens,
        completion_tokens,
    )

    context_files: list[str] | None = None
    if retrieved is not None:
        # Preserve first-occurrence order (already by descending score) and dedupe.
        seen: set[str] = set()
        context_files = []
        for c in retrieved.selected:
            if c.file_path not in seen:
                seen.add(c.file_path)
                context_files.append(c.file_path)
                if len(context_files) >= 10:
                    break

    result = ReviewResult(
        verdict=verdict,
        findings=findings,
        provider=provider.name,
        elapsed_ms=elapsed_ms,
        context_files=context_files,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )

    await _persist_run(
        input_kind="pr_url" if original_pr_url else "diff",
        pr_url=original_pr_url,
        repo_id=repo_id,
        diff=diff,
        verdict=str(verdict),
        provider_name=provider.name,
        elapsed_ms=elapsed_ms,
        findings=findings,
        context_files=context_files,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )
    return result


class ReviewService:
    """Stateless façade — methods correspond to the two input modes."""

    async def run_for_diff(self, diff: str, *, repo_id: UUID | None = None) -> ReviewResult:
        return await _run_chat(diff, repo_id=repo_id)

    async def run_for_url(self, pr_url: str, *, repo_id: UUID | None = None) -> ReviewResult:
        from codesensei.review.github_diff import fetch_pr_diff

        diff = await fetch_pr_diff(pr_url)
        return await _run_chat(diff, repo_id=repo_id, original_pr_url=pr_url)
