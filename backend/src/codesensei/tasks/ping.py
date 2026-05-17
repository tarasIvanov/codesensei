"""Trivial demo job that just stamps the current UTC time."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


async def ping_job(ctx: dict[str, Any]) -> dict[str, str]:
    return {"stamped_at": datetime.now(UTC).isoformat()}
