# Data Model: UX polish — drop Recent row, reformat tokens, write README

**Feature**: 014-ux-polish-and-readme
**Date**: 2026-05-21

This feature introduces ZERO new persisted entities. All deltas are computed or rendering-only.

---

## Entity 1 — `embedding_token_count` (computed integer, repo entity)

A read-time aggregate exposed on the repo wire shape. Not persisted.

**Source**: `SUM(code_chunks.token_count) GROUP BY repo_id`. The `code_chunks.token_count` column is `INTEGER NOT NULL` (introduced by feature 005 / ADR-007).

**Wire shape** (additive on existing `RepoEntry` dict from `IndexingService.list_repos`):

| Field | Type | Notes |
|-------|------|-------|
| `embedding_token_count` | integer | Sum of `token_count` over all currently-persisted chunks of this repo. `0` when the repo has zero chunks (empty source, or pre-feature row whose chunks predate the aggregate). |

**Invariants**:

- `embedding_token_count >= 0`.
- Re-index swap (T2 atomic in `replace_chunks`) replaces the chunk set; aggregate reflects the new set on the next `GET /api/repos`.
- Pre-feature persisted rows that still have chunks contribute their `token_count` sums correctly because `token_count` was already populated since feature 005.

---

## Entity 2 — `formatTokenLine` output string (rendered, history detail)

Pure UI string, not persisted.

**Inputs** (from the historical-run wire shape, feature 012):

| Field | Type | Notes |
|-------|------|-------|
| `prompt_tokens` | integer / null / undefined | |
| `completion_tokens` | integer / null / undefined | |
| `cost_usd` | number / null / undefined | |

**Output** (string or null):

| Condition | Output |
|-----------|--------|
| `prompt_tokens != null && completion_tokens != null && cost_usd != null` | `"{pt+ct} tokens · ~${cost.toFixed(4)}"` |
| `prompt_tokens != null && completion_tokens != null && cost_usd == null` | `"{pt+ct} tokens"` |
| Either token field `null` (and any field defined) | `"tokens N/A"` |
| All three fields `undefined` (type backward-compat path) | `null` (render nothing) |

---

## Entity 3 — README sections (markdown blocks)

Ordered set of textual blocks at the repository root. Plain Markdown. No data model semantics beyond presence + order:

1. Title + tagline (`# CodeSensei — Self-hosted AI Code Reviewer`)
2. Thesis context paragraph (Ukrainian) + one-sentence English summary
3. Three named differentiators (per ADR-011)
4. Quick start (numbered list, ≤ 5 steps)
5. Architecture brief (1 paragraph + bullet stack)
6. Features overview (1-line bullets)
7. Project docs map (links to `_decision_log.md`, `_mvp_scope.md`, `specs/`)
8. License note

---

## State transitions

None. All three entities are either pure read-time computations (Entity 1, Entity 2) or static documentation (Entity 3).
