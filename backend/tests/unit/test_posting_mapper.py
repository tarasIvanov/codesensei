"""Mapper: ReviewResult → GitHub Reviews API payload."""

from __future__ import annotations

from codesensei.posting.mapper import INLINE_COMMENT_CAP, SIDE, build_payload
from codesensei.review.schema import Finding, ReviewResult, Severity, Verdict


def _result(findings: list[Finding], verdict: Verdict = Verdict.COMMENT) -> ReviewResult:
    return ReviewResult(
        verdict=verdict,
        findings=findings,
        provider="openai",
        elapsed_ms=4218,
    )


def test_empty_findings_yields_no_comments_and_empty_body() -> None:
    payload = build_payload(_result([], verdict=Verdict.APPROVE), "APPROVE")
    assert payload["comments"] == []
    assert payload["event"] == "APPROVE"
    body = payload["body"]
    assert isinstance(body, str)
    assert body == ""


def test_three_located_findings_all_inline() -> None:
    findings = [
        Finding(file="a.py", line=10, severity=Severity.BLOCKER, message="m1"),
        Finding(file="b.py", line=20, severity=Severity.MAJOR, message="m2"),
        Finding(file="c.py", line=30, severity=Severity.MINOR, message="m3"),
    ]
    payload = build_payload(_result(findings, verdict=Verdict.REQUEST_CHANGES), "COMMENT")
    comments = payload["comments"]
    assert isinstance(comments, list)
    assert len(comments) == 3
    for c, f in zip(comments, findings, strict=True):
        assert c["path"] == f.file
        assert c["side"] == SIDE
        assert c["line"] == f.line
        assert isinstance(c["body"], str)
        assert f.severity.value in c["body"]
        assert f.message in c["body"]
    body = payload["body"]
    assert "### Findings without inline location" not in body
    assert "### Additional findings" not in body


def test_mixed_located_and_locationless_splits_correctly() -> None:
    findings = [
        Finding(file="a.py", line=1, severity=Severity.BLOCKER, message="inline-1"),
        Finding(file="b.py", line=2, severity=Severity.MAJOR, message="inline-2"),
        Finding(file="c.py", line=None, severity=Severity.MINOR, message="body-1"),
        Finding(file="d.py", line=None, severity=Severity.NIT, message="body-2"),
    ]
    payload = build_payload(_result(findings), "COMMENT")
    assert len(payload["comments"]) == 2
    body = payload["body"]
    assert isinstance(body, str)
    assert "### Findings without inline location" in body
    assert "body-1" in body
    assert "body-2" in body
    assert "inline-1" not in body
    assert "inline-2" not in body


def test_overflow_above_50_cap_goes_to_body_with_location_suffix() -> None:
    findings = [
        Finding(file=f"f{i}.py", line=i + 1, severity=Severity.MINOR, message=f"m{i}")
        for i in range(52)
    ]
    payload = build_payload(_result(findings), "COMMENT")
    assert len(payload["comments"]) == INLINE_COMMENT_CAP
    body = payload["body"]
    assert isinstance(body, str)
    assert "### Additional findings (beyond the 50-comment cap)" in body
    assert "`f50.py:51`" in body
    assert "`f51.py:52`" in body
    # The first 50 are inline, not in the body.
    assert "`f0.py:1`" not in body


def test_suggestion_optional_paragraph() -> None:
    f_with = Finding(file="a.py", line=3, severity=Severity.MAJOR, message="msg", suggestion="do x")
    f_without = Finding(file="a.py", line=4, severity=Severity.MAJOR, message="msg")
    payload = build_payload(_result([f_with, f_without]), "COMMENT")
    bodies = [c["body"] for c in payload["comments"]]
    assert "_Suggestion_: do x" in bodies[0]
    assert "_Suggestion_:" not in bodies[1]


def test_line_zero_treated_as_locationless() -> None:
    # Pydantic coerces line<=0 to None — see Finding._coerce_line.
    f = Finding(file="a.py", line=0, severity=Severity.MAJOR, message="zero")
    assert f.line is None
    payload = build_payload(_result([f]), "COMMENT")
    assert payload["comments"] == []
    assert "zero" in payload["body"]
