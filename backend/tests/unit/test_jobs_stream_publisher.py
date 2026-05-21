"""Unit tests for jobs_stream/publisher.py (feature 013)."""

from __future__ import annotations

import json

import pytest
from fakeredis.aioredis import FakeRedis

from codesensei.jobs_stream.publisher import channel_for, publish


def test_channel_naming():
    assert channel_for("abc-123") == "codesensei:job:abc-123"


@pytest.mark.asyncio
async def test_publish_init_frame_lands_on_channel():
    redis = FakeRedis()
    pubsub = redis.pubsub()
    job_id = "job-xyz"
    channel = channel_for(job_id)
    await pubsub.subscribe(channel)
    # Drain the subscribe-confirmation message.
    await pubsub.get_message(timeout=0.1)

    frame = {"kind": "init", "state": "running", "files_done": 0, "chunks_done": 0}
    await publish(redis, job_id, frame)

    received = await pubsub.get_message(timeout=1.0)
    assert received is not None
    assert received["type"] == "message"
    data = received["data"]
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    assert json.loads(data) == frame
    await pubsub.aclose()
    await redis.aclose()


@pytest.mark.asyncio
async def test_publish_progress_and_complete_in_order():
    redis = FakeRedis()
    pubsub = redis.pubsub()
    job_id = "job-progress"
    channel = channel_for(job_id)
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=0.1)

    frames = [
        {"kind": "progress", "files_done": 1, "chunks_done": 100, "current_file": "a.py"},
        {"kind": "progress", "files_done": 2, "chunks_done": 200, "current_file": "b.py"},
        {"kind": "complete", "state": "success", "final_files": 2, "final_chunks": 200},
    ]
    for frame in frames:
        await publish(redis, job_id, frame)

    received: list[dict] = []
    for _ in frames:
        msg = await pubsub.get_message(timeout=1.0)
        assert msg is not None and msg["type"] == "message"
        data = msg["data"]
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        received.append(json.loads(data))
    assert received == frames
    await pubsub.aclose()
    await redis.aclose()
