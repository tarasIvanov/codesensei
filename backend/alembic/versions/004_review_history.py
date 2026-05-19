"""review_runs + review_findings tables for history persistence (feature 009)

Revision ID: 004_review_history
Revises: 003_repos_chunks
Create Date: 2026-05-19 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "004_review_history"
down_revision = "003_repos_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_runs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "input_kind",
            sa.Text(),
            sa.CheckConstraint(
                "input_kind IN ('diff','pr_url')",
                name="review_runs_input_kind_check",
            ),
            nullable=False,
        ),
        sa.Column("pr_url", sa.Text(), nullable=True),
        sa.Column(
            "repo_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column(
            "verdict",
            sa.Text(),
            sa.CheckConstraint(
                "verdict IN ('approve','request_changes','comment')",
                name="review_runs_verdict_check",
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("finding_count", sa.Integer(), nullable=False),
        sa.Column(
            "has_temporal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("context_files", JSONB(), nullable=True),
    )

    op.create_table(
        "review_findings",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("review_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("file", sa.Text(), nullable=False),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column(
            "severity",
            sa.Text(),
            sa.CheckConstraint(
                "severity IN ('blocker','major','minor','nit')",
                name="review_findings_severity_check",
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("temporal_context", JSONB(), nullable=True),
        sa.UniqueConstraint("run_id", "position", name="review_findings_run_position_uniq"),
    )

    op.execute(
        "CREATE INDEX review_runs_created_at_id_idx "
        "ON review_runs (created_at DESC, id)"
    )


def downgrade() -> None:
    op.drop_index("review_runs_created_at_id_idx", table_name="review_runs")
    op.drop_table("review_findings")
    op.drop_table("review_runs")
