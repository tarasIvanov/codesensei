"""US1+US3: ReviewService with AsyncMock LLMProvider."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from codesensei.config import get_settings
from codesensei.providers import ProviderError
from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.schema import Severity, Verdict
from codesensei.review.service import ReviewService

_GOOD_DIFF = (
    "diff --git a/x.py b/x.py\n"
    "--- a/x.py\n"
    "+++ b/x.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _FakeProvider:
    def __init__(self, name: str, chat_mock: AsyncMock):
        self.name = name
        self._mock = chat_mock

    async def chat(self, messages, **kwargs):
        return await self._mock(messages, **kwargs)


def _install(monkeypatch, *, return_value=None, side_effect=None, provider_name="openai"):
    if side_effect is not None:
        mock = AsyncMock(side_effect=side_effect)
    else:
        mock = AsyncMock(return_value=return_value)
    fake = _FakeProvider(provider_name, mock)
    monkeypatch.setattr(
        "codesensei.review.service.get_llm_provider", lambda: fake
    )
    return mock, fake


def _envelope(findings, verdict="comment") -> str:
    return json.dumps({"verdict": verdict, "findings": findings})


async def test_run_for_diff_happy(monkeypatch):
    raw = _envelope(
        [{"file": "x.py", "line": 1, "severity": "major", "message": "ahem"}],
        verdict="request_changes",
    )
    _install(monkeypatch, return_value=raw)
    result = await ReviewService().run_for_diff(_GOOD_DIFF)
    assert result.verdict is Verdict.REQUEST_CHANGES
    assert result.provider == "openai"
    assert result.findings[0].severity is Severity.MAJOR
    assert result.elapsed_ms >= 0


async def test_run_for_diff_empty_findings(monkeypatch):
    _install(monkeypatch, return_value=_envelope([], verdict="approve"))
    result = await ReviewService().run_for_diff(_GOOD_DIFF)
    assert result.verdict is Verdict.APPROVE
    assert result.findings == []


async def test_run_for_diff_chat_kwargs(monkeypatch):
    mock, _ = _install(monkeypatch, return_value=_envelope([], verdict="approve"))
    await ReviewService().run_for_diff(_GOOD_DIFF)
    kwargs = mock.call_args.kwargs
    assert kwargs.get("temperature") == 0.1
    assert kwargs.get("max_tokens") == 4096


async def test_run_for_diff_translates_retryable_provider_error(monkeypatch):
    err = ProviderError("openai", "503 upstream blew up", retryable=True)
    _install(monkeypatch, side_effect=err)
    with pytest.raises(ReviewError) as exc:
        await ReviewService().run_for_diff(_GOOD_DIFF)
    assert exc.value.category is ReviewErrorCategory.PROVIDER_UNAVAILABLE
    assert exc.value.retryable is True


async def test_run_for_diff_translates_non_retryable_provider_error(monkeypatch):
    err = ProviderError("openai", "401 bad key", retryable=False)
    _install(monkeypatch, side_effect=err)
    with pytest.raises(ReviewError) as exc:
        await ReviewService().run_for_diff(_GOOD_DIFF)
    assert exc.value.category is ReviewErrorCategory.PROVIDER_UNAVAILABLE
    assert exc.value.retryable is False


async def test_run_for_diff_malformed_output(monkeypatch):
    _install(monkeypatch, return_value="this is not JSON, dawg")
    with pytest.raises(ReviewError) as exc:
        await ReviewService().run_for_diff(_GOOD_DIFF)
    assert exc.value.category is ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT
    assert exc.value.retryable is False


async def test_run_for_diff_oversized_payload(monkeypatch):
    monkeypatch.setenv("REVIEW_MAX_DIFF_BYTES", "1000")
    get_settings.cache_clear()
    mock, _ = _install(monkeypatch, return_value=_envelope([], verdict="approve"))
    huge = _GOOD_DIFF + "+" + ("x" * 2000) + "\n"
    with pytest.raises(ReviewError) as exc:
        await ReviewService().run_for_diff(huge)
    assert exc.value.category is ReviewErrorCategory.PAYLOAD_TOO_LARGE
    assert mock.call_count == 0  # never called the LLM


async def test_run_for_diff_timeout(monkeypatch):
    monkeypatch.setenv("REVIEW_LLM_TIMEOUT_S", "0.05")
    get_settings.cache_clear()

    async def hang(*args, **kwargs):
        await asyncio.sleep(5.0)
        return "{}"

    mock = AsyncMock(side_effect=hang)
    fake = _FakeProvider("openai", mock)
    monkeypatch.setattr("codesensei.review.service.get_llm_provider", lambda: fake)

    with pytest.raises(ReviewError) as exc:
        await ReviewService().run_for_diff(_GOOD_DIFF)
    assert exc.value.category is ReviewErrorCategory.PROVIDER_UNAVAILABLE
    assert exc.value.retryable is True
