"""ReviewService — orchestrates prompt → provider chat → strict parse → ReviewResult."""
from __future__ import annotations

import asyncio
import time
from uuid import UUID

from codesensei.config import get_settings
from codesensei.indexing.errors import IndexError, IndexErrorCategory
from codesensei.indexing.retrieval import RetrievalResult, RetrievalService
from codesensei.providers import ProviderError, get_llm_provider
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.parser import parse_review
from codesensei.review.prompt import build_messages
from codesensei.review.schema import ReviewResult


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


async def _run_chat(diff: str, *, repo_id: UUID | None = None) -> ReviewResult:
    _enforce_size(diff)

    retrieved: RetrievalResult | None = None
    if repo_id is not None:
        retrieved = await _retrieve_context(repo_id, diff)

    provider = get_llm_provider()
    messages = build_messages(
        diff,
        retrieved_chunks=retrieved.selected if retrieved else None,
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
    elapsed_ms = int((time.perf_counter() - started) * 1000)

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

    return ReviewResult(
        verdict=verdict,
        findings=findings,
        provider=provider.name,
        elapsed_ms=elapsed_ms,
        context_files=context_files,
    )


class ReviewService:
    """Stateless façade — methods correspond to the two input modes."""

    async def run_for_diff(self, diff: str, *, repo_id: UUID | None = None) -> ReviewResult:
        return await _run_chat(diff, repo_id=repo_id)

    async def run_for_url(self, pr_url: str, *, repo_id: UUID | None = None) -> ReviewResult:
        from codesensei.review.github_diff import fetch_pr_diff

        diff = await fetch_pr_diff(pr_url)
        return await _run_chat(diff, repo_id=repo_id)
