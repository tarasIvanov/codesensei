# Contract — `worker` field in the `/healthz` envelope

Additive change to the existing healthz envelope (introduced in 001, extended in 002 with `providers`). This feature adds a single field, `worker`, with three possible values.

---

## Wire-shape delta

**Before this feature** (002 baseline):

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "extensions": {"vector": "ok"},
  "providers": {"llm": "ok", "embedding": "ok"}
}
```

**After this feature**:

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "extensions": {"vector": "ok"},
  "providers": {"llm": "ok", "embedding": "ok"},
  "worker": "ok"
}
```

`worker` value space:

| Value          | Meaning                                                                          |
|----------------|----------------------------------------------------------------------------------|
| `"ok"`         | Heartbeat key exists in Redis and is fresher than `worker_heartbeat_stale_s`.    |
| `"down"`       | Redis is reachable, but the heartbeat is missing or older than the threshold.    |
| `"unreachable"`| Redis itself is unreachable. (Note: this also flips `redis: "down"` separately.) |

`failing[]` (present on degraded responses) does **not** include `worker` — consistent with the pattern from `providers.llm` / `providers.embedding`. The `worker` value is **informational only**.

---

## Probe implementation contract

`probe_worker()` lives next to `probe_db` / `probe_redis` / `probe_llm_provider` / `probe_embedding_provider` in `healthcheck.py`. Signature:

```python
async def probe_worker() -> Literal["ok", "down", "unreachable"]: ...
```

Behaviour:

1. Connect to Redis using `settings.redis_url` with a 1-second timeout.
2. Read `arq:health-check:default`.
3. If the value parses as an ISO-8601 timestamp newer than `now() - settings.worker_heartbeat_stale_s` → `"ok"`.
4. If parses but stale, or key missing → `"down"`.
5. On `redis.exceptions.RedisError` / `asyncio.TimeoutError` → `"unreachable"`.

The handler runs this probe **in parallel** with the existing four probes via `asyncio.gather(..., return_exceptions=False)`, with a 3 s wall-clock cap.

---

## Logging

`probe_worker.failure` (WARNING) on `unreachable`. No INFO log per probe (otherwise every 5 s healthcheck spams the logs); a single summarised `probe.healthz` line at INFO is emitted from the handler, as today.
