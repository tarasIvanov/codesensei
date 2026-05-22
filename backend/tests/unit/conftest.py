"""Unit-test fixtures."""

from collections.abc import Iterator

import pytest
from structlog.testing import capture_logs


@pytest.fixture
def captured_log_events() -> Iterator[list[dict]]:
    """Capture structlog events emitted during the test.

    Uses `structlog.testing.capture_logs()` so it works regardless of prior
    structlog config from other tests.
    """
    with capture_logs() as cap:
        yield cap
