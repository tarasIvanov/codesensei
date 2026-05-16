"""US1: ReviewRequest validation + Finding model."""
from __future__ import annotations

import pytest

from codesensei.review.errors import ReviewError, ReviewErrorCategory
from codesensei.review.schema import (
    Finding,
    ReviewRequest,
    Severity,
    looks_like_unified_diff,
)

_GOOD_DIFF = (
    "diff --git a/x.py b/x.py\n"
    "--- a/x.py\n"
    "+++ b/x.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)


def test_request_accepts_unified_diff():
    req = ReviewRequest(diff=_GOOD_DIFF)
    assert req.diff == _GOOD_DIFF
    assert req.pr_url is None


def test_request_accepts_pr_url():
    req = ReviewRequest(pr_url="https://github.com/octocat/Hello-World/pull/1")
    assert req.pr_url.endswith("/pull/1")
    assert req.diff is None


def test_request_rejects_both_diff_and_url():
    with pytest.raises(ReviewError) as exc:
        ReviewRequest(diff=_GOOD_DIFF, pr_url="https://github.com/o/r/pull/1")
    assert exc.value.category is ReviewErrorCategory.INVALID_INPUT
    assert "either" in exc.value.message.lower()


def test_request_rejects_neither():
    with pytest.raises(ReviewError) as exc:
        ReviewRequest()
    assert exc.value.category is ReviewErrorCategory.INVALID_INPUT


def test_request_rejects_empty_strings():
    with pytest.raises(ReviewError) as exc:
        ReviewRequest(diff="", pr_url="")
    assert exc.value.category is ReviewErrorCategory.INVALID_INPUT


def test_request_rejects_non_diff_text():
    with pytest.raises(ReviewError) as exc:
        ReviewRequest(diff="hello, this is not a diff at all")
    assert exc.value.category is ReviewErrorCategory.INVALID_INPUT
    assert "unified diff" in exc.value.message.lower()


def test_request_rejects_malformed_pr_url():
    bad_urls = [
        "http://github.com/o/r/pull/1",         # http, not https
        "https://gitlab.com/o/r/pull/1",        # not github
        "https://github.com/o/r/pulls/1",       # pulls (plural) — wrong
        "https://github.com/o/r/pull/abc",      # non-numeric pr id
        "https://github.com/o/r/issues/1",      # issues, not pull
    ]
    for url in bad_urls:
        with pytest.raises(ReviewError) as exc:
            ReviewRequest(pr_url=url)
        assert exc.value.category is ReviewErrorCategory.INVALID_INPUT


def test_looks_like_unified_diff_detects_git_header():
    assert looks_like_unified_diff(_GOOD_DIFF)


def test_looks_like_unified_diff_accepts_minus_plus_only():
    text = "--- a/foo\n+++ b/foo\n@@\n-x\n+y\n"
    assert looks_like_unified_diff(text)


def test_looks_like_unified_diff_rejects_prose():
    assert not looks_like_unified_diff("just some prose")
    assert not looks_like_unified_diff("")


def test_finding_rejects_unknown_severity():
    with pytest.raises(ValueError):
        Finding(file="a", line=1, severity="lol", message="x")  # type: ignore[arg-type]


def test_finding_rejects_zero_or_negative_line():
    with pytest.raises(ValueError):
        Finding(file="a", line=0, severity=Severity.MINOR, message="x")
    with pytest.raises(ValueError):
        Finding(file="a", line=-3, severity=Severity.MINOR, message="x")


def test_finding_accepts_null_line():
    f = Finding(file="a", line=None, severity=Severity.NIT, message="general comment")
    assert f.line is None


def test_finding_truncates_long_message():
    long = "x" * 3000
    f = Finding(file="a", line=1, severity=Severity.MAJOR, message=long)
    assert len(f.message) == 2000
    assert f.message.endswith("…")


def test_finding_truncates_long_suggestion():
    long = "y" * 5000
    f = Finding(
        file="a", line=1, severity=Severity.MAJOR, message="m", suggestion=long
    )
    assert f.suggestion is not None
    assert len(f.suggestion) == 4000
    assert f.suggestion.endswith("…")


def test_finding_keeps_short_suggestion_intact():
    f = Finding(
        file="a", line=1, severity=Severity.NIT, message="m", suggestion="short"
    )
    assert f.suggestion == "short"
