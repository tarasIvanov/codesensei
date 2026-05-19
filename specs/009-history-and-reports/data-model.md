# Data Model — 009 Review History & Reports

Two new relational tables, one new index, one new alembic revision. No JSONB schema beyond preserving the `temporal_context` payload shipped by feature 008. No new pydantic Settings field. No new compose service.

## Schema overview

```
┌─────────────────────────────────────┐         ┌─────────────────────────────────────────┐
│ review_runs                         │         │ review_findings                         │
│─────────────────────────────────────│         │─────────────────────────────────────────│
│ id              UUID PK             │  1:N    │ id              UUID PK                 │
│ created_at      TIMESTAMPTZ default │ ───────▶│ run_id          UUID FK → review_runs   │
│ input_kind      TEXT (CHECK)        │         │                 ON DELETE CASCADE       │
│ pr_url          TEXT NULL           │         │ position        INTEGER NOT NULL        │
│ repo_id         UUID FK → repos NULL│         │ file            TEXT NOT NULL           │
│                 ON DELETE SET NULL  │         │ line            INTEGER NULL            │
│ diff            TEXT NOT NULL       │         │ severity        TEXT NOT NULL (CHECK)   │
│ verdict         TEXT (CHECK)        │         │ message         TEXT NOT NULL           │
│ provider        TEXT NOT NULL       │         │ suggestion      TEXT NULL               │
│ elapsed_ms      INTEGER NOT NULL    │         │ temporal_context JSONB NULL             │
│ finding_count   INTEGER NOT NULL    │         │                                         │
│ has_temporal    BOOLEAN default F   │         │ UNIQUE (run_id, position)               │
│ context_files   JSONB NULL          │         └─────────────────────────────────────────┘
└─────────────────────────────────────┘
        │
        ▼
INDEX review_runs_created_at_id_idx
      ON review_runs (created_at DESC, id)
```

## `review_runs`

| Column          | Type          | Constraints                                                                                  | Notes |
|-----------------|---------------|----------------------------------------------------------------------------------------------|-------|
| `id`            | UUID          | PK, default `gen_random_uuid()`                                                              | Opaque, never reused on prune. |
| `created_at`    | TIMESTAMPTZ   | NOT NULL, default `now()`                                                                    | Used for ORDER BY + LRU prune. |
| `input_kind`    | TEXT          | NOT NULL, CHECK (`input_kind IN ('diff','pr_url')`)                                          | Distinguishes posted-back-able runs from diff-only. |
| `pr_url`        | TEXT          | NULL                                                                                         | Present iff `input_kind = 'pr_url'`. |
| `repo_id`       | UUID          | NULL, FK → `repos(id) ON DELETE SET NULL`                                                    | Nullable so deleting `/repos` row preserves run (FR-020). |
| `diff`          | TEXT          | NOT NULL                                                                                     | Normalised unified diff verbatim. Capped upstream at 200 KB (`review_max_diff_bytes`). |
| `verdict`       | TEXT          | NOT NULL, CHECK (`verdict IN ('approve','request_changes','comment')`)                       | LLM output. |
| `provider`      | TEXT          | NOT NULL                                                                                     | Active provider name (`openai` / `anthropic` / `ollama`). |
| `elapsed_ms`    | INTEGER       | NOT NULL                                                                                     | Wall-clock LLM call. |
| `finding_count` | INTEGER       | NOT NULL                                                                                     | Cached for list view. |
| `has_temporal`  | BOOLEAN       | NOT NULL, default FALSE                                                                      | True iff any finding has non-null `temporal_context`. |
| `context_files` | JSONB         | NULL                                                                                         | List of file paths from RAG retrieval (mirrors live response). |

### Indexes

- `review_runs_pkey` (auto, on `id`).
- `review_runs_created_at_id_idx` on `(created_at DESC, id)` — backs the listing query (`ORDER BY created_at DESC LIMIT N`) and the prune query (`ORDER BY created_at ASC LIMIT M`).

## `review_findings`

| Column             | Type     | Constraints                                                                              | Notes |
|--------------------|----------|------------------------------------------------------------------------------------------|-------|
| `id`               | UUID     | PK, default `gen_random_uuid()`                                                          | |
| `run_id`           | UUID     | NOT NULL, FK → `review_runs(id) ON DELETE CASCADE`                                       | |
| `position`         | INTEGER  | NOT NULL, UNIQUE on `(run_id, position)`                                                 | Stable order; matches LLM emission order. |
| `file`             | TEXT     | NOT NULL                                                                                 | |
| `line`             | INTEGER  | NULL                                                                                     | NULL for file-level findings. |
| `severity`         | TEXT     | NOT NULL, CHECK (`severity IN ('blocker','major','minor','nit')`)                        | Backend enum (per ADR-012). |
| `message`          | TEXT     | NOT NULL                                                                                 | Capped upstream at 2000 chars. |
| `suggestion`       | TEXT     | NULL                                                                                     | Capped upstream at 4000 chars. |
| `temporal_context` | JSONB    | NULL                                                                                     | Verbatim from feature 008's pydantic dump, or NULL. |

### Indexes

- `review_findings_pkey` (auto, on `id`).
- `review_findings_run_id_position_uniq` (auto from UNIQUE constraint) — backs the detail view's `ORDER BY position` query.

## ORM models (sketch)

```python
# backend/src/codesensei/reviews_history/models.py
class ReviewRun(Base):
    __tablename__ = "review_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    input_kind: Mapped[str]
    pr_url: Mapped[str | None]
    repo_id: Mapped[UUID | None] = mapped_column(ForeignKey("repos.id", ondelete="SET NULL"))
    diff: Mapped[str]
    verdict: Mapped[str]
    provider: Mapped[str]
    elapsed_ms: Mapped[int]
    finding_count: Mapped[int]
    has_temporal: Mapped[bool]
    context_files: Mapped[list[str] | None] = mapped_column(JSONB)
    findings: Mapped[list["ReviewFinding"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="ReviewFinding.position",
    )


class ReviewFinding(Base):
    __tablename__ = "review_findings"
    __table_args__ = (UniqueConstraint("run_id", "position"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("review_runs.id", ondelete="CASCADE"))
    position: Mapped[int]
    file: Mapped[str]
    line: Mapped[int | None]
    severity: Mapped[str]
    message: Mapped[str]
    suggestion: Mapped[str | None]
    temporal_context: Mapped[list[dict] | None] = mapped_column(JSONB)
    run: Mapped[ReviewRun] = relationship(back_populates="findings")
```

## Pydantic wire shapes

### `ReviewRunSummary` (listing response item)

```python
class ReviewRunSummary(BaseModel):
    id: UUID
    created_at: datetime
    input_kind: Literal["diff", "pr_url"]
    pr_url: str | None
    verdict: Literal["approve", "request_changes", "comment"]
    provider: str
    elapsed_ms: int
    finding_count: int
    has_temporal: bool
```

### `ReviewRunDetail` (detail response)

```python
class ReviewRunDetail(BaseModel):
    id: UUID
    created_at: datetime
    input_kind: Literal["diff", "pr_url"]
    pr_url: str | None
    diff: str                       # full stored diff
    verdict: Literal[...]
    provider: str
    elapsed_ms: int
    findings: list[Finding]         # re-uses review/schema.py:Finding (includes temporal_context)
    context_files: list[str] | None
```

The `findings` array is the same `Finding` pydantic model from `review/schema.py` — re-export rather than redefine, so the SPA `FindingsList` rendering branch is identical between live and historical paths (FR-007).

## What is NOT in the data model

- No `created_by` / multi-user column.
- No `error_envelope` column for failed runs — failed reviews are not persisted (FR-004).
- No `raw_llm_response` column — only the parsed findings are stored (Out of Scope §).
- No vector column — this feature is plain relational.
- No `app_settings` change — the 1000-row cap is a module-private constant.
