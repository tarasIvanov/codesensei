# Phase 0 Research: UX polish — drop Recent row, reformat tokens, write README

**Feature**: 014-ux-polish-and-readme
**Date**: 2026-05-21

Records implementation-level decisions. No `[NEEDS CLARIFICATION]` markers in spec.md.

---

## Decision 1: Embedding-token aggregate — shape + place

**Decision**: One SQL `SELECT repo_id, SUM(token_count) AS total FROM code_chunks WHERE repo_id = ANY(:ids) GROUP BY repo_id` executed inside `indexing/store.py:get_embedding_token_counts(session, repo_ids)`. Returns `dict[UUID, int]` with missing repos defaulting to 0 at the service-layer call site.

**Rationale**:

- `code_chunks.token_count` is `INTEGER NOT NULL` (ADR-007); SUM is exact integer arithmetic.
- One round-trip for all repos avoids N+1 across the `/repos` list (≤ 50 repos at thesis scale, but the right shape regardless).
- Living in `store.py` matches the CRUD layout — no architectural drift.
- Service-layer default-to-zero keeps the SQL clean (no `COALESCE` rendered for missing groups) and the response shape stable.

**Alternatives considered**:

- **Per-repo subquery in `list_repos_ordered`**: introduces N+1, even at thesis scale. Rejected.
- **Cache aggregate on `repos` row**: requires a column + a maintenance path on every re-index swap → DB schema change → Constitution II hard trigger. Rejected as scope-creep.
- **Compute in Python from a `selectinload(Repo.chunks)` eager load**: pulls all chunk rows into memory just to sum a column. Wasteful. Rejected.

---

## Decision 2: `/history` token-line shape

**Decision**: render `N tokens · ~$X.XXXX` with `N = prompt_tokens + completion_tokens`. Edge cases:

- both null (legacy row) → `tokens N/A`
- both present, cost null (unknown pricing pair / Ollama) → `N tokens` (no cost segment)
- both undefined (frontend type backward-compat for pre-feature wire) → render nothing (return null from helper)

**Rationale**: matches user explicit preference ("без розділення in/out"). One number reads faster on the detail card than the two-number split. The branch ordering keeps `tokens N/A` only when fields are explicitly null on the wire, not when the type is missing them.

**Alternatives considered**:

- **Keep `in / out` split + add total**: redundant — user explicitly asked for total-only. Rejected.
- **Drop the line entirely on /history too**: would lose the audit-trail signal that 012 added. Rejected by spec FR-002.

---

## Decision 3: `/repos` rendering position + formatting

**Decision**: insert a new `<dt>Embedding tokens</dt><dd>{{ formatThousands(r.embedding_token_count ?? 0) }} tokens</dd>` row inside the existing per-repo `<dl>`, between the existing `Chunks` row and the `Indexed at` row. `formatThousands(n)` uses `n.toLocaleString('en-US')` (built-in, no new dep).

**Rationale**:

- Sibling-row placement (rather than a new section) keeps visual rhythm consistent with the rest of the repo metadata.
- Between Chunks and Indexed at is the natural read-order (chunks → tokens → when).
- `toLocaleString('en-US')` renders `1234567` as `1,234,567`. Stdlib; consistent across all modern browsers; matches the existing English-locale UI defaults elsewhere in the app.
- Suffix "tokens" matches the unit convention used on `/history`.

**Alternatives considered**:

- **Custom thousand-separator function**: no benefit over `toLocaleString`. Rejected.
- **Dollar amount alongside**: user explicit "лише tokens без $". Rejected.
- **Show as a Badge above the `<dl>`**: badges are reserved for status signals (verdict, status, ignore-count). Out-of-band placement for a metadata datum confuses semantics. Rejected.

---

## Decision 4: "Recent:" chip-strip removal — preserve `<datalist>` backing

**Decision**: delete the visible chip-strip render block + the `recentPrs` ref reads it depends on. Keep:

- The `RECENT_PR_KEY` constant.
- The `readList<string>(RECENT_PR_KEY)` initial load (still drives the `<datalist>`).
- The `pushToRecentList<string>(RECENT_PR_KEY, trimmed, 10)` call inside `submit()`.
- The `<datalist>` element bound to the URL input.

**Rationale**: spec FR-005 explicitly requires the persistence side-effect to keep working. The chip strip was a duplicate affordance; the input autocomplete provides the same surface with zero extra screen real estate.

**Alternatives considered**:

- **Delete the persistence too**: breaks the autocomplete. Rejected.
- **Hide the chip strip behind a collapse**: still occupies layout space (collapse header). Rejected — outright removal is cleaner.

---

## Decision 5: README language + length

**Decision**: English README, single Ukrainian paragraph at the top citing thesis context (author Тарас Іванов + bachelor-thesis goal). Target length ~200-300 lines including code blocks. Sections in order per FR-006:

1. Tagline + title
2. Thesis context (single Ukrainian paragraph + English summary)
3. Three differentiators (per ADR-011)
4. Quick start (5 steps)
5. Architecture brief (1 paragraph + stack bullets)
6. Features overview (1-line bullets)
7. Project docs map (`_decision_log.md`, `_mvp_scope.md`, `specs/`)
8. License note (educational use, thesis project)

**Rationale**:

- Codebase comments + ADRs are mostly English; defaulting English keeps grep + diff predictable. The Ukrainian paragraph at the top serves the thesis-committee audience without forcing a full bilingual layout.
- 200-300 line budget keeps the README scannable. Deeper detail lives in `specs/` per FR-008.
- No license file added separately — the short note in README is sufficient until thesis defence outcome.

**Alternatives considered**:

- **Full Ukrainian README**: cleaner for committee but breaks parity with codebase comments + GitHub repo discoverability for any English-reading visitor. Rejected.
- **Full bilingual side-by-side**: doubles the maintenance surface for no clear gain. Rejected.

---

## Decision 6: Frontend backward-compat on `embedding_token_count`

**Decision**: `RepoEntry.embedding_token_count?: number | null` (optional). The Vue template renders `r.embedding_token_count ?? 0`. Backend always supplies the field after this feature ships, but the type stays optional so older deployments (or a stale frontend talking to a stale backend) degrade gracefully to `0 tokens` instead of `undefined tokens`.

**Rationale**: matches the additive pattern from features 012/013 where new optional fields were treated as optional on the type. Zero added defensive code; nullish-coalescing handles the missing-field case at zero runtime cost.

---

## Open clarifications

None.
