"""repos + code_chunks tables for RAG indexing

Revision ID: 003_repos_chunks
Revises: 002_app_settings
Create Date: 2026-05-17 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "003_repos_chunks"
down_revision = "002_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "source_kind",
            sa.Text(),
            sa.CheckConstraint("source_kind IN ('https','local')", name="repos_source_kind_check"),
            nullable=False,
        ),
        sa.Column("default_branch", sa.Text(), nullable=True),
        sa.Column("embedding_provider", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "code_chunks",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "repo_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column(
            "start_line",
            sa.Integer(),
            sa.CheckConstraint("start_line >= 1", name="code_chunks_start_line_check"),
            nullable=False,
        ),
        sa.Column(
            "end_line",
            sa.Integer(),
            sa.CheckConstraint("end_line >= start_line", name="code_chunks_end_line_check"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "token_count",
            sa.Integer(),
            sa.CheckConstraint("token_count >= 0", name="code_chunks_token_count_check"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1536), nullable=False),
    )

    op.create_index("code_chunks_repo_id_idx", "code_chunks", ["repo_id"])
    op.execute(
        "CREATE INDEX code_chunks_embedding_hnsw_idx "
        "ON code_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("code_chunks_embedding_hnsw_idx", table_name="code_chunks")
    op.drop_index("code_chunks_repo_id_idx", table_name="code_chunks")
    op.drop_table("code_chunks")
    op.drop_table("repos")
