"""URL parser for the posting service."""

from __future__ import annotations

import pytest

from codesensei.posting.service import parse_pr_url
from codesensei.review.errors import ReviewError, ReviewErrorCategory


def test_well_formed_url() -> None:
    assert parse_pr_url("https://github.com/foo/bar/pull/42") == ("foo", "bar", 42)


def test_trailing_slash_rejected() -> None:
    with pytest.raises(ReviewError) as exc:
        parse_pr_url("https://github.com/foo/bar/pull/42/")
    assert exc.value.category == ReviewErrorCategory.INVALID_INPUT


def test_http_not_https_rejected() -> None:
    with pytest.raises(ReviewError) as exc:
        parse_pr_url("http://github.com/foo/bar/pull/42")
    assert exc.value.category == ReviewErrorCategory.INVALID_INPUT


def test_missing_pull_number_rejected() -> None:
    with pytest.raises(ReviewError) as exc:
        parse_pr_url("https://github.com/foo/bar/pull/abc")
    assert exc.value.category == ReviewErrorCategory.INVALID_INPUT
