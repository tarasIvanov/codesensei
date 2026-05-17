# Contract — `POST /api/jobs/ping` + `GET /api/jobs/{job_id}`

Minimal job-queue surface that proves arq is wired. No business logic.

---

## `POST /api/jobs/ping`

- **Request**: empty body, `Content-Type: application/json` (any JSON object is accepted; ignored).
- **Effect**: enqueues `ping_job` on the default arq queue via `arq.connections.create_pool(...).enqueue_job(...)`.

### Success — `202 Accepted`

```json
{
  "job_id": "0193b4a6-...",
  "submitted_at": "2026-05-17T12:34:55.901Z"
}
```

The job-id is the value returned by `enqueue_job(...)`'s `.job_id` (arq's own opaque id; never used as anything but a string).

### Errors

- `502 queue_unavailable` if Redis is not reachable.
- `500 internal` otherwise.

---

## `GET /api/jobs/{job_id}`

- **Path param**: `job_id` — opaque string. Must match arq's job-id pattern (UUID-like).

### Success — `200 OK`

```json
{
  "job_id": "0193b4a6-...",
  "status": "complete",
  "submitted_at": "2026-05-17T12:34:55.901Z",
  "completed_at": "2026-05-17T12:34:56.789Z",
  "result": {"stamped_at": "2026-05-17T12:34:56.789Z"}
}
```

For in-flight or queued jobs, omit `completed_at` and `result`, and set `status` to `pending` or `in_progress` as reported by `Job.status(...)`.

### Not-found — `404 OK-shape`

```json
{
  "job_id": "0193b4a6-...",
  "status": "not_found"
}
```

Returned with HTTP `404` so curl-style callers see a clear failure but the wire shape stays uniform.

### Errors

- `400 invalid_input` if `job_id` is not a sensible string (empty, oversized).
- `502 queue_unavailable` if Redis is not reachable.

---

## Idempotency / concurrency

- `POST /api/jobs/ping` is **not** idempotent — each call enqueues a fresh job. There is no client de-dup.
- `GET /api/jobs/{job_id}` is read-only and side-effect free.

---

## Logging

One structured log line per request:

- `event="jobs.ping.enqueued"` with `job_id` on enqueue success.
- `event="jobs.poll.read"` with `job_id` and `status` on lookup.
- `event="jobs.failed"` with `error_category` on any failure.

No business content of the job (`stamped_at`, here trivial; in future features the payload may carry user content) is logged at INFO; the `result` field is for the wire only.
