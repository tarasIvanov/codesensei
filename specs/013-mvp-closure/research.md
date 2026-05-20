# Phase 0 Research: MVP closure — custom-ignore + live index progress

**Feature**: 013-mvp-closure
**Date**: 2026-05-21

Consolidates implementation-level decisions implied by the spec. No `[NEEDS CLARIFICATION]` markers remained in spec.md, so research records the choices downstream tasks will execute.

---

## Decision 1: `.codesensei-ignore` parser implementation

**Decision**: hand-rolled parser using only `pathlib` + `fnmatch` from stdlib. No `pathspec` library, no `gitignore-parser` library.

- Read the file as bytes once; reject if `len > 4 KB` (FR-005).
- Decode UTF-8 (replace errors); split on `\n`.
- For each line in source order:
  - strip trailing whitespace + `\r`;
  - if line is empty after strip → drop;
  - if first non-whitespace char is `#` → drop;
  - if line ends with `/` → mark as directory pattern, strip the trailing `/`;
  - otherwise → mark as file/glob pattern.
- Stop after collecting 200 entries; emit a structured warning `codesensei_ignore_truncated` with `total_lines`, `kept` (= 200), and the `repo_id`.
- Matching: a walked path matches a directory pattern when ANY of its `relative_to(root).parts` matches the pattern via `fnmatch.fnmatchcase`. A walked path matches a file pattern when `fnmatch.fnmatchcase(rel_path_as_posix, pattern)` returns True OR when `fnmatch.fnmatchcase(path.name, pattern)` returns True (the `**/*.snap` and `*.generated.ts` cases respectively).

**Rationale**:

- The file format is intentionally a strict subset of gitignore (no negation, no character classes beyond fnmatch's). The subset is small enough that a 30-line parser is the lowest-risk shape.
- `pathspec` is widely used but pulls a dependency for one screen of code, and its semantics (gitignore-exact) include negation + anchored patterns we don't want.
- `fnmatch` is in stdlib, deterministic, and well-tested. The `**` wildcard is supported by `fnmatch.fnmatch` since Python 3.13 — but the indexer runs Python 3.12. So `**/*.snap` is handled by the "filename-only" match leg (since `*.snap` against `path.name` catches every nested `.snap`); `dist/**` works because `dist/` is parsed as a directory pattern and matches any walked path with `dist` in its parts.

**Alternatives considered**:

- **`pathspec`**: one dep for ~50 LoC of value; brings gitignore semantics we explicitly don't want (negation).
- **`gitignore-parser`**: smaller dep but ditto — full gitignore including negation.
- **Hand-roll regex from each glob**: more flexible than fnmatch but every regex compile is a runtime hazard if the pattern contains `\E` etc. Not worth the surface.

---

## Decision 2: Redis pub/sub as the fan-out

**Decision**: progress events flow `arq worker → publish to channel codesensei:job:<job_id> → WS endpoint subscribes via redis.asyncio.pubsub()`.

- Worker side: `await ctx["redis"].publish(channel, json.dumps(frame))` next to each existing `_logger.info("indexing_progress", ...)` call. Throttled to ≤ 2/s via a small `last_publish_ts` tracker inside `index_repo_job`.
- API side: WS handler does `pubsub = redis.pubsub(); await pubsub.subscribe(channel)`. The subscribe loop runs `async for message in pubsub.listen()`, forwarding each `message["data"]` (a JSON string) to the WebSocket via `ws.send_text`.
- Init frame: emitted by the WS handler itself after `subscribe.subscribe()` returns, with state read from the existing arq job context via `arq.connections.RedisSettings` + `arq.jobs.Job(job_id, redis)`. Avoids a race where the client misses progress that fired between job-state lookup and channel subscribe (subscribe happens FIRST).
- Complete frame: emitted by the worker on terminal state inside the `try/except/finally` of `index_repo_job`. WS handler watches for `kind == "complete"` and closes with code 1000.

**Rationale**:

- arq already runs on Redis (ADR-007). Reusing it for pub/sub is a single-component story — no new infra, no new container.
- pub/sub fan-out is exactly the semantics we want (1 publisher, N subscribers, no replay, no persistence). Multiple SPA tabs on the same `job_id` each get the same stream.
- The "subscribe first, then read state for init frame" ordering eliminates the missed-event window without buffering.

**Alternatives considered**:

- **Redis streams (XADD/XREAD)**: gives replay semantics we don't need (spec out-of-scope: "no replay/buffered events on reconnect"), and complicates trim policy.
- **In-process asyncio.Queue with worker writing via HTTP back to api**: introduces a network hop on every progress event, plus the api could have multiple workers (in a future deployment) so the broadcast surface would need a sticky-routing solution. Pub/sub sidesteps this entirely.
- **Polling DB rows for progress**: turns progress into a DB write per file — fights ADR-007 and would dirty the indexing critical path.

---

## Decision 3: WebSocket route shape + close codes

**Decision**: `WS /api/jobs/{job_id}/stream` (matches the existing GET `/api/jobs/{job_id}` URL family).

- On connect:
  - Subscribe to `codesensei:job:<job_id>`.
  - Look up arq job state. If unknown → `await ws.close(code=4404, reason="job_not_found")`.
  - Send `InitFrame` with current state.
- Loop:
  - For each `pubsub.listen()` message → forward as a text frame.
  - If forwarded frame has `kind == "complete"` → `await ws.close(code=1000)` and exit.
- On client disconnect: `pubsub.unsubscribe(); pubsub.aclose()`. No reconnect-side state to clean (no per-client buffer).
- 4404 chosen for "job not found" because RFC 6455 defines 4000–4999 as application-specific close codes; 4404 mirrors HTTP 404 mnemonically.
- 1000 (normal closure) on graceful completion.
- Anything else (network drop, server-side error) bubbles as a non-1000 close → SPA falls back to polling per FR-012.

**Rationale**:

- URL co-location with the existing `GET` polling endpoint makes the WS upgrade discoverable and testable from the same route family.
- Close codes are the standard wire signal for client-side fallback decisions; no need for an extra error frame.

**Alternatives considered**:

- **Send an `error` frame instead of close-with-code**: more verbose, requires the client to interpret two failure modes. Close codes are simpler.
- **Top-level `WS /api/stream` with a query param `?job_id=...`**: hides the relationship to `/api/jobs/{id}` and complicates testing.

---

## Decision 4: Persistence of `.codesensei-ignore` patterns

**Decision**: persist as `codesensei_ignore_patterns JSONB NULL` on the existing `repos` table; ONE alembic migration `006_repos_codesensei_ignore.py` (down_revision `005_review_run_tokens`).

- Written at the end of `_run_index_inline` / `index_repo_job`, after the chunk swap commits successfully.
- Stored value: the parsed pattern list (post-truncation), preserving source order. Empty file → `NULL` (not `[]`), matching FR-014's "applied at least one pattern" condition for badge rendering.
- Read by `GET /api/repos` and surfaced on `RepoSummary` / `RepoDetail` as `codesensei_ignore_patterns: list[str] | None`.

**Rationale**:

- FR-014 says the badge must render on `/repos` page after reload. The patterns live in the source tree which is wiped after indexing → caching is required.
- The `repos` row is the natural cache key (one-to-one with index runs). JSONB is the right shape for a small ordered string list; no need for a separate `repo_ignore_patterns` table.
- Re-read every index run (FR-016) means the cache is always the truth as of the last run.

**Alternatives considered**:

- **Ephemeral, only returned on the index-response payload**: violates FR-014 on reload (rejected in plan.md Complexity Tracking).
- **Separate `repo_ignore_patterns` table with FK + position**: over-modelled for ≤ 200 strings per repo. JSONB is industry-standard for this profile.
- **TEXT column with newline-delimited patterns**: forces parse-on-read, no schema-level guarantee of list shape, and breaks JSON-mode clients.

---

## Decision 5: Frontend WebSocket composable + fallback

**Decision**: `frontend/src/composables/useJobStream.ts` exposes:

```ts
export function useJobStream(
  jobId: Ref<string | null>,
  onFrame: (frame: ProgressFrame | CompleteFrame | InitFrame) => void,
): { fallbackToPolling: Ref<boolean>; close: () => void }
```

- On `jobId` non-null: create `new WebSocket(\`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/jobs/${jobId.value}/stream\`)`.
- `onopen` → `fallbackToPolling.value = false`.
- `onmessage` → `onFrame(JSON.parse(event.data))`.
- `onclose` → if `code === 1000` (clean completion), leave `fallbackToPolling` as-is (it was false). Otherwise set `fallbackToPolling.value = true` so the caller's polling timer takes over.
- `onerror` → same as a non-1000 close.
- On `jobId` becoming null (e.g. job finished) → close the socket; never auto-reconnect.

- `ReposPage.vue` keeps its existing 2 s polling timer. On mount of a per-job progress row:
  - Call `useJobStream(jobId, applyFrame)`.
  - Watch `fallbackToPolling`: when `false`, pause the polling timer for that job; when `true`, resume it.
- The polling endpoint is unchanged; the SPA continues to call `GET /api/jobs/{id}` as before in fallback.

**Rationale**:

- Composable owns ONE concern: WS transport selection signal. The polling code stays where it is (no rewrites of existing logic). The signal is a `Ref<boolean>`, the lowest-coupling Vue primitive.
- No auto-reconnect on WS — keeps the composable trivial. FR-012 says fall back to polling; reconnect-with-replay is explicitly out of scope.

**Alternatives considered**:

- **Composable owns both transports + state**: doubles the API surface and complicates testing. Rejected.
- **One transport, switchable via env flag**: forces operators to choose between live and reliable; the whole point of "WS preferred, polling fallback" is they don't.

---

## Decision: ADR-016 contents (drafted at the implementation gate)

The ADR that MUST be written before any production code lands. Drafted here so `tasks.md` can reference it as T002; the actual prose lives in `_decision_log.md` as a NEW entry directly above ADR-015.

```
### ADR-016: Operator-facing index controls — `.codesensei-ignore` + live progress stream
- Date: 2026-05-21
- Status: accepted
- Decision: Two operator-facing index controls land in one feature pack.
  (1) A `.codesensei-ignore` file at the indexed repo root extends the
  built-in indexer skip rules with project-specific globs. Format: one
  fnmatch-style glob per line; `#` comments and blank lines ignored;
  trailing `/` marks a directory pattern; hard caps 200 patterns / 4 KB.
  No negation, no character-class escapes beyond fnmatch. The parsed
  pattern list is persisted on the `repos` row as a NEW JSONB column
  `codesensei_ignore_patterns NULL` (alembic 006_repos_codesensei_ignore.py,
  down_revision=005_review_run_tokens) so the `/repos` badge survives
  page reload; re-read from disk on every index run (no stale-cache risk).
  (2) Indexing progress is fanned out from the arq worker via Redis
  pub/sub (channel `codesensei:job:<job_id>`) and surfaced to the SPA
  through a NEW WebSocket endpoint `WS /api/jobs/{job_id}/stream` on
  the same FastAPI app. The existing 2 s polling endpoint stays as a
  graceful fallback; the SPA's `useJobStream` composable signals when
  to suspend/resume the polling timer. No new container, no new env
  var; existing nginx config inside the `frontend/` Dockerfile gains
  `proxy_http_version 1.1` + `Upgrade`/`Connection` headers on the
  `/api/` location to forward WS upgrades.
- Why: Closes the last two MUST checkboxes from `_mvp_scope.md §2.3`
  (FR-4.3 custom ignore, FR-6.1 real-time progress). Without (1)
  operators with non-conventional repos silently index generated
  code, polluting RAG and inflating embedding cost. Without (2) the
  defence demo shows a 2 s lag between worker progress and UI, which
  reads as "frozen" on long index runs. The combined ADR is justified
  because both surfaces ship in the same pack and the two non-trivial
  trade-offs (persistence shape for ignore + transport choice for
  progress) are interlocking — splitting them would create two ADRs
  with overlapping context.
- Notes: NFR-3.1 confirmation — `.codesensei-ignore` patterns are NOT
  credentials; the JSONB column holds operator-authored globs. The WS
  channel carries progress integers + file paths from the indexed
  source tree (same boundary as today's polling response). No new
  auth surface on the WS endpoint (single-user self-hosted threat
  model). Throttling: ≤ 2 progress events/s, coalesced inside
  `index_repo_job`. Reconnect/replay deferred (out of scope for v1).
  Pattern semantics: directory pattern (`vendor/`) matches any walked
  path with that segment; file pattern (`*.generated.ts`) matches by
  filename OR by relative-path fnmatch. Truncation/oversize → graceful
  warning logs, never an indexing crash. Supersedes nothing.
```

---

## Decision 6: Frontend nginx WebSocket upgrade

**Decision**: ensure the frontend container's nginx config forwards WebSocket upgrade headers for the `/api/` location.

```nginx
location /api/ {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    # ... existing headers ...
}
```

**Rationale**:

- Default nginx config buffers HTTP/1.0 and strips `Connection` headers, killing the WS upgrade handshake. The four lines above are the standard nginx WS-proxy idiom.
- `proxy_read_timeout 3600s` covers long index runs that go 5+ minutes without progress events (rare but possible on first-time embedding of a large repo).

**Alternatives considered**:

- **Bypass nginx by exposing api:8000 directly in dev**: works for local smoke but breaks production deploys, where the compose proxy chain IS the deployment shape.
- **Custom subdomain / port for WS**: violates Constitution V (single-command deploy, no extra port mapping).

---

## Open clarifications

None. All spec-driven decisions are resolved; no `[NEEDS CLARIFICATION]` markers remained after spec.md.
