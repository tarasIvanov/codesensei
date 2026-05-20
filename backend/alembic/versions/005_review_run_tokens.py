"""token usage + cost estimate columns on review_runs (feature 012)

Revision ID: 005_review_run_tokens
Revises: 004_review_history
Create Date: 2026-05-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "005_review_run_tokens"
down_revision = "004_review_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_runs",
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "review_runs",
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "review_runs",
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("review_runs", "cost_usd")
    op.drop_column("review_runs", "completion_tokens")
    op.drop_column("review_runs", "prompt_tokens")
