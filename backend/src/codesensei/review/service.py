"""ReviewService — orchestrates prompt → provider chat → strict parse → ReviewResult."""
from __future__ import annotations

import asyncio
import time

from codesensei.config import get_settings
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


async def _run_chat(diff: str) -> ReviewResult:
    _enforce_size(diff)
    provider = get_llm_provider()
    messages = build_messages(diff)
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
    return ReviewResult(
        verdict=verdict,
        findings=findings,
        provider=provider.name,
        elapsed_ms=elapsed_ms,
    )


class ReviewService:
    """Stateless façade — methods correspond to the two input modes."""

    async def run_for_diff(self, diff: str) -> ReviewResult:
        return await _run_chat(diff)

    async def run_for_url(self, pr_url: str) -> ReviewResult:
        from codesensei.review.github_diff import fetch_pr_diff

        diff = await fetch_pr_diff(pr_url)
        return await _run_chat(diff)
