# Phase 1 — Data Model: Infrastructure Scaffold

This spec ships **no business tables**. The single alembic migration enables the `vector` PostgreSQL extension; downstream feature specs introduce the actual schema.

## Persistent state

| Element | Type | Notes |
|---|---|---|
| `vector` extension | Postgres extension | Enabled at first migration. Required for HNSW indexing in future specs (ADR-004). |
| `postgres_data` | Docker named volume | Holds the Postgres data directory across `docker compose down` (NOT across `down -v`). |

## Alembic migration ledger

| Revision | Path | Description |
|---|---|---|
| `001_enable_pgvector` | `backend/alembic/versions/001_enable_pgvector.py` | `CREATE EXTENSION IF NOT EXISTS vector;` (idempotent). Down-revision: `None` (root). Down-method: `DROP EXTENSION IF EXISTS vector;`. |

**Migration content** (canonical body for the file):

```python
"""enable pgvector

Revision ID: 001_enable_pgvector
Revises:
Create Date: 2026-05-12 00:00:00.000000
"""
from alembic import op

revision = "001_enable_pgvector"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
```

## Migration policy (recap from `plan.md`)

- Hand-written migrations only at commit time. `alembic revision --autogenerate` is allowed during development as a starting point but the diff must be reviewed and likely rewritten before commit.
- One logical schema change per migration.
- Migrations run automatically on api container startup (entrypoint executes `alembic upgrade head` before `uvicorn`).
- Downgrade methods are mandatory for every migration even when "destructive" — required to keep the local dev loop reversible.

## Future-spec entities (reserved, NOT in this spec)

Listed only to clarify what this scaffold intentionally leaves out:

- `repositories`, `chunks` (with `vector` embedding column), `chunk_dependencies`, `reports`, `report_comments`, `settings`, `pr_runs`. Each lands in its own feature spec.
