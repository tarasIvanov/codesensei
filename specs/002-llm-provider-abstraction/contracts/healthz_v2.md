# Contract: `/healthz` v2 envelope (provider extension)

Extends the v1 envelope from `specs/001-infra-scaffold/contracts/healthz.md`. Backward-compatible: every v1 field is preserved; the new `providers` object is purely additive.

---

## Endpoints

Same routes as v1:

- `GET /healthz` — root mount on the API service.
- `GET /api/healthz` — alias for the nginx proxy path.

Both return identical envelopes.

## Response — `200 OK` (overall ok)

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "extensions": { "vector": "ok" },
  "providers": {
    "llm": "ok",
    "embedding": "ok"
  }
}
```

## Response — `503 Service Unavailable` (overall degraded)

`status` is set to `"degraded"` **only when** db, redis, or vector is non-ok (v1 behaviour, unchanged). Provider states do not flip overall status — see FR-013.

```json
{
  "status": "degraded",
  "db": "down",
  "redis": "ok",
  "extensions": { "vector": "ok" },
  "providers": {
    "llm": "ok",
    "embedding": "ok"
  },
  "failing": ["db"]
}
```

## `providers` object

| Field | Type | Possible values |
|-------|------|-----------------|
| `llm` | `str` | `"ok"` \| `"unconfigured"` \| `"unreachable"` |
| `embedding` | `str` | `"ok"` \| `"unconfigured"` \| `"unreachable"` |

Semantics per `data-model.md > ProviderState`. The strings appear verbatim in the Vue dashboard badges.

## Probe behaviour (server-side)

- The two provider probes run **in parallel** with `db` and `redis` probes inside the existing `asyncio.gather(...)` block. Total timeout (`asyncio.wait_for`) is unchanged at 3 s.
- A provider probe MUST NOT contribute to `failing[]`. The `failing[]` list is reserved for db/redis/vector.
- Provider probes MUST NOT log at `error` level when returning `unconfigured` (that's expected operator state, not a fault). `unreachable` is logged at `warning` level.

## Field stability

| Field | v1 | v2 | Stability |
|-------|----|----|-----------|
| `status` | yes | yes | unchanged |
| `db` | yes | yes | unchanged |
| `redis` | yes | yes | unchanged |
| `extensions.vector` | yes | yes | unchanged |
| `failing[]` | yes (optional) | yes (optional) | unchanged — provider names NEVER appear here |
| `providers.llm` | — | yes | new |
| `providers.embedding` | — | yes | new |

Existing v1 consumers (any tooling reading `status`/`db`/`redis`/`extensions.vector`) continue to work without changes.

## Frontend contract

`frontend/src/App.vue` MUST render two new badges using the same dot-color UX as the existing four. Color rule:

- `"ok"` → green (`#16a34a`)
- `"unconfigured"` → grey (`#9ca3af`)
- `"unreachable"` → red (`#dc2626`)

The TypeScript `HealthEnvelope` type alias in `App.vue` MUST be extended with `providers: { llm: ProviderStatus; embedding: ProviderStatus }`.
