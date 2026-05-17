"""US3: classify_http_status truth table + ProviderError formatting."""

from __future__ import annotations

import pytest

from codesensei.providers import ProviderError, classify_http_status


@pytest.mark.parametrize(
    "code,expected",
    [
        (500, True),
        (502, True),
        (503, True),
        (599, True),
        (429, True),
        (408, True),
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (418, False),
        (499, False),
        (200, False),
        (301, False),
    ],
)
def test_classify_http_status(code, expected):
    assert classify_http_status(code) is expected


def test_provider_error_str_format():
    err = ProviderError("openai", "rate limit", retryable=True)
    assert err.provider == "openai"
    assert err.message == "rate limit"
    assert err.retryable is True
    assert str(err) == "openai: rate limit"


def test_provider_error_config_terminal():
    err = ProviderError("config", "bad value", retryable=False)
    assert err.retryable is False
    assert "config: bad value" == str(err)
