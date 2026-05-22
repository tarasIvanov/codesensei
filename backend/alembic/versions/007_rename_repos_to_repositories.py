"""rename repos table to repositories (feature 016)

Revision ID: 007_rename_repos_to_repositories
Revises: 006_repos_codesensei_ignore
Create Date: 2026-05-23 00:00:00.000000

Cosmetic DB-level rename. Postgres carries the foreign-key references
on ``code_chunks.repo_id`` forward automatically through the rename.
The check constraint name is updated to keep naming consistent.
"""

from alembic import op

revision = "007_rename_repos_to_repositories"
down_revision = "006_repos_codesensei_ignore"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("repos", "repositories")
    op.execute(
        "ALTER TABLE repositories "
        "RENAME CONSTRAINT repos_source_kind_check "
        "TO repositories_source_kind_check"
    )
    op.execute("ALTER INDEX repos_pkey RENAME TO repositories_pkey")
    op.execute("ALTER INDEX repos_source_key RENAME TO repositories_source_key")


def downgrade() -> None:
    op.execute("ALTER INDEX repositories_source_key RENAME TO repos_source_key")
    op.execute("ALTER INDEX repositories_pkey RENAME TO repos_pkey")
    op.execute(
        "ALTER TABLE repositories "
        "RENAME CONSTRAINT repositories_source_kind_check "
        "TO repos_source_kind_check"
    )
    op.rename_table("repositories", "repos")
