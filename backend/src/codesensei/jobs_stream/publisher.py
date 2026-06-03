"""Redis pub/sub publisher for job progress (feature 013)."""

from __future__ import annotations

import json
from typing import Any


def channel_for(job_id: str) -> str:
    return f"codesensei:jobs:{job_id}"


async def publish(redis: Any, job_id: str, frame: dict) -> None:
    """Publish one JSON-encoded frame on the per-job channel.

    Throttling lives at the call site (`index_repo_job`) so the publisher
    itself stays a thin transport.
    """
    await redis.publish(channel_for(job_id), json.dumps(frame))
