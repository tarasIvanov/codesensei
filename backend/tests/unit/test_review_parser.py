"""US1: LLM-output parser — happy + fail-fast on malformed."""

from __future__ import annotations

import json

import pytest

from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.parser import parse_review
from codesensei.review.schema import Severity, Verdict


def _envelope(findings: list[dict], verdict: str = "comment") -> str:
    return json.dumps({"verdict": verdict, "findings": findings})


def test_parses_happy_envelope():
    raw = _envelope(
        [{"file": "a.py", "line": 4, "severity": "major", "message": "null check"}],
        verdict="request_changes",
    )
    verdict, findings = parse_review("openai", raw)
    assert verdict is Verdict.REQUEST_CHANGES
    assert len(findings) == 1
    assert findings[0].severity is Severity.MAJOR
    assert findings[0].file == "a.py"


def test_parses_empty_findings_as_approve():
    raw = _envelope([], verdict="approve")
    verdict, findings = parse_review("openai", raw)
    assert verdict is Verdict.APPROVE
    assert findings == []


def test_strips_json_fence():
    body = _envelope([], verdict="approve")
    fenced = "```json\n" + body + "\n```"
    verdict, findings = parse_review("ollama", fenced)
    assert verdict is Verdict.APPROVE
    assert findings == []


def test_strips_plain_fence():
    body = _envelope([], verdict="approve")
    fenced = "```\n" + body + "\n```"
    verdict, findings = parse_review("ollama", fenced)
    assert verdict is Verdict.APPROVE


def test_rejects_non_json():
    with pytest.raises(ReviewError) as exc:
        parse_review("anthropic", "this is not JSON, dawg")
    assert exc.value.category is ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT


def test_rejects_empty_string():
    with pytest.raises(ReviewError) as exc:
        parse_review("openai", "   \n   ")
    assert exc.value.category is ReviewErrorCategory.PROVIDER_MALFORMED_OUTPUT


def test_rejects_non_object_top_level():
    with pytest.raises(ReviewError):
        parse_review("openai", "[1, 2, 3]")


def test_rejects_missing_verdict():
    raw = json.dumps({"findings": []})
    with pytest.raises(ReviewError):
        parse_review("openai", raw)


def test_rejects_missing_findings():
    raw = json.dumps({"verdict": "approve"})
    with pytest.raises(ReviewError):
        parse_review("openai", raw)


def test_rejects_unknown_verdict():
    raw = _envelope([], verdict="merge_blocked")
    with pytest.raises(ReviewError):
        parse_review("openai", raw)


def test_rejects_unknown_severity():
    raw = _envelope([{"file": "a", "line": 1, "severity": "catastrophic", "message": "x"}])
    with pytest.raises(ReviewError):
        parse_review("openai", raw)


def test_rejects_non_integer_line():
    raw = _envelope([{"file": "a", "line": "many", "severity": "minor", "message": "x"}])
    with pytest.raises(ReviewError):
        parse_review("openai", raw)


def test_rejects_missing_file():
    raw = _envelope([{"line": 1, "severity": "minor", "message": "x"}])
    with pytest.raises(ReviewError):
        parse_review("openai", raw)


def test_rejects_missing_message():
    raw = _envelope([{"file": "a", "line": 1, "severity": "minor"}])
    with pytest.raises(ReviewError):
        parse_review("openai", raw)


def test_truncates_long_message_not_rejected():
    long = "x" * 3000
    raw = _envelope([{"file": "a", "line": 1, "severity": "nit", "message": long}])
    _, findings = parse_review("openai", raw)
    assert len(findings[0].message) == 2000
    assert findings[0].message.endswith("…")


def test_truncates_long_suggestion_not_rejected():
    long = "y" * 5000
    raw = _envelope(
        [
            {
                "file": "a",
                "line": 1,
                "severity": "nit",
                "message": "m",
                "suggestion": long,
            }
        ]
    )
    _, findings = parse_review("openai", raw)
    assert findings[0].suggestion is not None
    assert len(findings[0].suggestion) == 4000
