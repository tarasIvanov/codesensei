"""app_settings table

Revision ID: 002_app_settings
Revises: 001_enable_pgvector
Create Date: 2026-05-17 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "002_app_settings"
down_revision = "001_enable_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
