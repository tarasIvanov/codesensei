# Contract: `GET /healthz`

Backend dependency-status probe. Drives:
- the compose-level `healthcheck:` for the `api` service (FR-005);
- the frontend status badges (US3);
- future CI smoke tests.

## Endpoint

```
GET /healthz
```

- **Auth**: none.
- **Request body**: none.
- **Query params**: none.
- **Response content-type**: `application/json; charset=utf-8`.

## Healthy response — HTTP 200

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "extensions": {
    "vector": "ok"
  }
}
```

Returned when **all** of the following hold:
- A `SELECT 1` round-trip against Postgres succeeds within 3 s.
- `SELECT 1 FROM pg_extension WHERE extname = 'vector'` returns exactly one row.
- `PING` against Redis returns `PONG` within 3 s.

## Degraded response — HTTP 503

```json
{
  "status": "degraded",
  "db": "ok",
  "redis": "down",
  "extensions": {
    "vector": "ok"
  },
  "failing": ["redis"]
}
```

Field semantics:

| Field | Type | Values | Meaning |
|---|---|---|---|
| `status` | string | `ok` \| `degraded` | Top-level rollup. `degraded` whenever any field is anything other than `ok`. |
| `db` | string | `ok` \| `down` | Postgres `SELECT 1` round-trip result. |
| `redis` | string | `ok` \| `down` | Redis `PING` result. |
| `extensions.vector` | string | `ok` \| `missing` \| `unknown` | `ok` if the `pg_extension` query returns the `vector` row; `missing` if it returns zero rows; `unknown` if the `db` probe itself failed and we couldn't run the extension query. |
| `failing` | string[] | subset of `["db", "redis", "vector"]` | Components that contributed to the `degraded` status. Always present on 503; absent on 200. |

## Latency budget

- p95 ≤ **50 ms** in fully-healthy state on localhost.
- Hard handler timeout ≤ **3 s** across both probes combined (probes run in parallel with `asyncio.gather`, wrapped in `asyncio.wait_for(timeout=3.0)`).
- On handler timeout: response is HTTP 503 with `db` and/or `redis` flagged as `down` for whichever probe did not complete.

## Logging

Each call MUST emit one structured log line with keys: `event="healthz"`, `status` (matching the response field), `db`, `redis`, `extensions.vector`, `duration_ms`. No credentials, no environment-variable values. (Constitution Workflow §3.)

## Future evolution (NOT in this spec)

- Add `queue` field when arq worker lands (separate spec).
- Add per-provider `llm` and `embedding` fields when adapters land (separate specs).
- A separate `/readyz` endpoint may diverge from `/healthz` if startup-vs-liveness semantics ever need to differ.
