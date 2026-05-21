# Contract: `WS /api/jobs/{job_id}/stream`

**Status**: NEW. Introduced by feature 013.
**Source of truth**: `backend/src/codesensei/jobs_stream/router.py` + `schema.py`.

## Endpoint

```
WS /api/jobs/{job_id}/stream
```

Co-located with the existing `GET /api/jobs/{job_id}` polling endpoint (URL-family parity). No query parameters, no headers required beyond standard WS-upgrade.

## Handshake

- Client sends a standard WebSocket upgrade against the endpoint.
- Server:
  1. Subscribes to Redis channel `codesensei:job:<job_id>` (BEFORE looking up state — eliminates the missed-event window).
  2. Looks up arq job state via `arq.jobs.Job(job_id, redis).status()` + `.result_info()`.
  3. If state is `JobStatus.not_found` → `await ws.close(code=4404, reason="job_not_found")`.
  4. Otherwise → send `InitFrame` reflecting current state.
- Time budget on handshake: ≤ 1 s (SC-002).

## Frame schemas

### `InitFrame` (always the first text frame)

```json
{
  "kind": "init",
  "state": "queued" | "running" | "success" | "failed" | "cancelled",
  "files_total": 1234 | null,
  "files_done": 567,
  "chunks_done": 789,
  "started_at": "2026-05-21T15:42:11Z",
  "eta_seconds": 42 | null
}
```

### `ProgressFrame` (zero or more)

```json
{
  "kind": "progress",
  "files_done": 568,
  "files_total": 1234 | null,
  "chunks_done": 790,
  "current_file": "src/foo/bar.py" | null
}
```

Sent at the worker's natural file-completion pace, coalesced to ≤ 2 per second.

### `CompleteFrame` (exactly one, terminal)

```json
{
  "kind": "complete",
  "state": "success" | "failed" | "cancelled",
  "error_category": "payload_too_large" | null,
  "error_message": "Diff exceeds the 200 KB limit. Try a smaller change." | null,
  "final_files": 1234,
  "final_chunks": 1500
}
```

After `CompleteFrame`, the server calls `ws.close(code=1000)`.

## Close codes

| Code | Reason | Client action |
|------|--------|---------------|
| 1000 | Normal closure (terminal frame sent) | Stop polling timer if it was suspended; render final state. |
| 4404 | Job ID not found | Fall back to polling, which will return the same not-found response from `GET /api/jobs/{id}`. |
| Anything else | Network drop, server error | Fall back to polling at the existing 2 s interval. |

## Redis pub/sub channel

- **Channel name**: `codesensei:job:<job_id>` (one per job UUID).
- **Publisher**: `backend/src/codesensei/jobs_stream/publisher.py` exposes `async def publish(redis, job_id, frame) -> None`. Called from `index_repo_job` next to each existing `_logger.info("indexing_progress", ...)` site, plus once at the terminal state.
- **Subscriber**: the WS endpoint, via `redis.asyncio.Redis.pubsub()`.
- **Throttle**: publisher tracks `last_publish_ts` per job; skips `progress` frames published within 0.5 s of the previous. The `init` and `complete` frames are NEVER throttled.
- **Message format**: each message body is `json.dumps(frame)`; the WS handler forwards via `ws.send_text(message["data"])` without re-parsing.

## Invariants

- Frames within a single connection are ordered: `init` → 0+ `progress` → `complete` → close.
- A `complete` frame is always the last frame; no further frames are sent on the same connection after it.
- No frames are buffered server-side after disconnect. Client must reconnect (or fall back) to recover progress.
- The endpoint does NOT authenticate (single-user self-hosted).

## Backward compatibility

- The existing `GET /api/jobs/{id}` endpoint is UNCHANGED in shape and behaviour.
- Clients that do not use the WS endpoint continue to function identically.
- Frontend tries WS first; on failure, falls back to polling per FR-012.
