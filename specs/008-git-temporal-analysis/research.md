# Research — 008 Git Temporal Analysis

Resolves the open questions surfaced in `plan.md` (R1–R12). Every decision is paired with the alternatives rejected and the reason.

## R1 — Line-history extraction: `git log -L` vs `git blame`

- **Decision**: Use `git log -L <start>,<end>:<file>` per line window.
- **Rationale**: `-L` walks only the commits that *touch the range* (O(touched-commits)). `blame` walks every line of the file at HEAD (O(file-lines)) and answers a different question (per-line authorship). The feature wants commit-level signal — "what commits have been editing this range" — which is exactly what `-L` returns natively. Capping with `-n <max_commits>` plus a hard wall-clock timeout via `asyncio.wait_for` keeps the cost bounded.
- **Alternatives considered**:
  - `git blame -L`: returns line-level authorship at HEAD, lacks the historical-commit list. Out of fit.
  - `git rev-list HEAD -- <file>`: cheaper but file-granular (not line-window-aware) — would surface every commit touching the whole file, including commits irrelevant to the window. Too noisy.
  - `git log --follow -p -- <file>`: file-granular *with* patch bodies — heavier than `-L` for the same noise problem.
- **Implementation knob**: `--pretty=format:%H%x09%h%x09%ae%x09%aI%x09%s` (TAB-separated, no patch body) → cheap to parse, no shell-escape concerns. Separately, `--unified=0 --no-color` is run only on the first 8 commits to count `hunk_lines_changed`.

## R2 — Fast clone shape

- **Decision**: `git clone --filter=blob:none --no-checkout <source> <cache_dir>` on first lookup per repo per process.
- **Rationale**: `--filter=blob:none` skips blob downloads but fetches all commits + trees (cheap). `--no-checkout` skips materialising the working tree (cheaper). The combination gives `git log -L` everything it needs — blobs needed for line-range expansion are lazily fetched (partial-clone protocol), and we never need a working tree. Real-world cost on a warm host: ≤ 2 s for repos with ≤ 5 k commits.
- **Alternatives considered**:
  - `--depth N` shallow clone: caps history at N commits → useless for the feature (the whole point is historical depth).
  - `--bare`: gives us .git without a working tree, but loses the `--filter=blob:none` lazy-fetch hook for `-L`'s on-demand blob loads.
  - `git fetch` over an existing `git init`-ed empty dir: more machinery for the same result; first-time UX is slower.

## R3 — `/var/tmp` vs `/tmp`

- **Decision**: Cache root at `/var/tmp/codesensei-temporal/`.
- **Rationale**: `/tmp` is often `tmpfs` (RAM-backed) and is wiped by some service managers on process restart; `/var/tmp` is required by the FHS to survive across reboots and PID-1 restarts. We want cache amortisation across requests in one container — `/var/tmp` matches that semantic without a host-mounted volume. Container *recreation* (compose down + up) is acceptable to blow it away (Assumptions / spec.md).
- **Alternatives considered**:
  - `/tmp`: faster (tmpfs) but ephemeral within the container — defeats SC-005.
  - Project-mounted `./data/temporal-cache`: would survive across container *recreation* but introduces a new host volume in `docker-compose.yml` (FR-015 / V).
  - Existing `chunks_dir` Postgres-managed storage: pgvector is not a git store. Off-fit.

## R4 — Cache key derivation

- **Decision**: `sha1(canonical_source.encode("utf-8")).hexdigest()` → 40-char hex directory name under `/var/tmp/codesensei-temporal/`.
- **Rationale**: stable filesystem-safe per repo identity; no URL leaks via `ls`. Canonical form comes from the same `normalise_source` used by `indexing/clone.py` (strip trailing `/`, strip trailing `.git`) so a re-index that drifts on trailing slash still hits the same cache bucket.
- **Alternatives considered**:
  - Direct URL → percent-encoded path: leaks the source URL to a `ls`, fragile under SELinux relabel rules.
  - `repos.id` UUID: requires a repo row to exist before the cache is keyed — re-introduces a DB round-trip into the hot path even when we already have the source.

## R5 — Cache eviction policy

- **Decision**: mtime LRU at cap = 5 entries. On each successful lookup, `os.utime(cache_dir, None)` to bump mtime. When the cache root has > 5 sub-directories, `shutil.rmtree(oldest)`.
- **Rationale**: filesystem-native (no in-memory LRU dict to drift away from on-disk truth), survives crashes, eviction cost is O(cache_size) ≤ 5 entries — trivial.
- **Alternatives considered**:
  - In-process `functools.lru_cache`-style dict: state lost on every restart, gets out of sync if disk pruned out-of-band.
  - LRU by access count / Redis-keyed: overkill for 5-slot working set.
  - Time-based TTL only (no count cap): could grow unboundedly if many repos cycled within the TTL window.

## R6 — Parallelism

- **Decision**: `asyncio.TaskGroup` for per-file fan-out; per-call `asyncio.wait_for(per_call_timeout_s=1.5)` ceiling; outer caller (`fetch_temporal_pool_for_review`) tracks elapsed against a 2.0 s soft budget and cancels still-pending children when crossed.
- **Rationale**: matches the async discipline rule in the Constitution Tech Stack §. TaskGroup propagates cancellation cleanly, so we don't leak processes when the budget breach fires.
- **Alternatives considered**:
  - Sequential `await` chain: simple but doubles wall-clock on multi-file reviews.
  - `asyncio.gather(*, return_exceptions=True)`: doesn't propagate cancellation as cleanly as TaskGroup; we'd need manual cancel logic.
  - `concurrent.futures.ThreadPoolExecutor`: violates "no blocking sync call on request path" (FR-018).

## R7 — Line windows from PR diff

- **Decision**: Reuse `review/github_diff.py:parse_hunks()` to get RHS hunk ranges per file. Collapse hunks ≤ 5 lines apart into a single window. Keep at most 3 windows per file (lowest-line wins). Clamp each to 200 lines (FR-006).
- **Rationale**: matches the existing patch-parser already used by the feature 007 code-context snippet — keeps the diff parser as the single source of truth on what "the lines this PR touched" means. The collapse-3-windows cap prevents pathologically scattered PRs (one-line edits in 50 places in the same file) from generating 50 git calls.
- **Alternatives considered**:
  - One window per hunk (no collapse): allows up to N hunks · per-call timeout — pathological PR drains the whole budget.
  - One window per file (whole-file range): noisy entries from unrelated commits.

## R8 — Subprocess hygiene

- **Decision**: All git invocations via `asyncio.create_subprocess_exec` (positional args list — no shell interpolation). Explicit `cwd=cache_dir`. `env={"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/true", "PATH": os.environ["PATH"]}` to defeat interactive auth pop on private/redirected repos. `stderr=asyncio.subprocess.PIPE` so we can log a one-line summary, not echo it in the response.
- **Rationale**: matches the pattern already in `indexing/clone.py`. No shell-injection surface, no interactive prompt risk, no env leakage.
- **Alternatives considered**:
  - `subprocess.run`: blocking — fails FR-018.
  - `aiofiles + subprocess`: doesn't async-spawn the process; doesn't help.

## R9 — Routing pool → findings

- **Decision**: After `fetch_temporal_pool_for_review` returns `dict[file_path, list[(LineWindow, list[TemporalEntry])]]`, iterate findings post-parse: for each finding with `(file, line)` both present, look up `pool.get(finding.file)`; pick the entries whose `window` brackets `finding.line` (the first match wins; windows don't overlap by construction since we collapse during pool construction); attach as `finding.temporal_context`. Empty / no-match findings get `None`.
- **Rationale**: O(findings × windows-per-file) with a constant factor ≤ 3 — negligible. Single-pass, no extra git invocation, deterministic.
- **Alternatives considered**:
  - Re-fetch per finding: doubles the git call count for no gain; defeats the time budget.
  - Have the LLM emit window IDs we map back: layers prompt-format risk for no clarity win.

## R10 — Volatility-badge threshold

- **Decision**: ≥ 3 entries → badge shown ("N changes"); < 3 → no badge.
- **Rationale**: A single rewrite + a follow-up fix is the normal cadence for "stable code being actively maintained" — 2 entries. ≥ 3 commits in the most-recent five (the cap on the list) is disproportionate churn against the baseline. The cutoff was chosen for readability; the cap on the list is itself the soft top.
- **Alternatives considered**:
  - ≥ 2: catches normal maintenance, too noisy.
  - ≥ 4: under-flags real volatility on top of a 5-cap list (only fires when *most* of the cap is full).

## R11 — No env-vars in v1

- **Decision**: Cache directory, count cap, per-call timeout, total budget, stale window all live as module-private constants in `review/git_temporal.py`. No `.env.example` change, no docs change for operators.
- **Rationale**: Out-of-Scope item in spec.md — operator-tunable knobs are deferred until a real operator asks. The footprint of adding a runtime env var is high (operator docs, .env.example, README, `_loader` plumbing) for zero v1 demand.
- **Alternatives considered**:
  - Expose all five constants as `CODESENSEI_TEMPORAL_*` env vars: adds operator surface area for hypothetical tuning needs.

## R12 — No DB schema migration

- **Decision**: `temporal_context` is a transient compute output, lives only in the in-memory `Finding` instance and on the wire. The DB is untouched.
- **Rationale**: persisting per-finding history would mean either (a) writing findings to the DB (we don't, by design — they're returned and shown) or (b) caching the temporal pool itself in the DB (the runtime cache already serves that, on-disk). Both add complexity without value.
- **Alternatives considered**:
  - Persist temporal entries as a side table for offline analysis: out of scope (Out of Scope, spec.md — no history dashboard).

---

## Cross-cutting research notes

### Container has `git` already
The API container's `backend/Dockerfile` installs git as a build-and-runtime dependency for `indexing/clone.py`. No image rebuild is required for this feature. The image already ships git ≥ 2.40 which supports `--filter=blob:none --no-checkout` and `git log -L` with the `--pretty=format:` placeholders we use.

### Concurrency under one Python process
The API runs under one Uvicorn worker by default. Two concurrent reviews against the *same* repo will both hit the same cache directory; we guard against the "two processes cloning into the same dir" race with a per-cache-key `asyncio.Lock` resident in the module. The lock is keyed by the sha1 cache key and is `WeakValueDictionary`-backed so it disappears when no longer needed.

### Test seam: `_clone_for_test`
Production code reads `_clone_or_reuse(repo_source)` → `Path`. The unit-test seam swaps that function for one that returns a pytest-tmp_path-managed working tree (set up with the test fixture). This sidesteps real `git clone`-over-network in unit tests, while integration tests mock the whole `fetch_temporal_context` callable.

### What happens on a force-pushed history rewind
Spec edge case: the cache's `git fetch --prune` (run when mtime > 1 h) follows the new remote tip. Until that hour passes, the cache continues to serve the old history. The user can force-evict by recreating the API container — same behaviour as the existing RAG cache invalidation discipline.
