"""codesensei_ignore_patterns column on repos (feature 013)

Revision ID: 006_repos_codesensei_ignore
Revises: 005_review_run_tokens
Create Date: 2026-05-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "006_repos_codesensei_ignore"
down_revision = "005_review_run_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repos",
        sa.Column("codesensei_ignore_patterns", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repos", "codesensei_ignore_patterns")
