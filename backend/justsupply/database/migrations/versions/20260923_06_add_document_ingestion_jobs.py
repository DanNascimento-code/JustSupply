"""Add durable asynchronous document ingestion jobs.

Revision ID: 20260923_06
Revises: 20260916_05
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260923_06"
down_revision: str | Sequence[str] | None = "20260916_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("source_title", sa.String(length=300), nullable=False),
        sa.Column("source_provider", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=2083), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_document_ingestion_jobs_status",
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_documents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_ingestion_jobs_brand_id",
        "document_ingestion_jobs",
        ["brand_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_ingestion_jobs_status",
        "document_ingestion_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_ingestion_jobs_status", table_name="document_ingestion_jobs")
    op.drop_index("ix_document_ingestion_jobs_brand_id", table_name="document_ingestion_jobs")
    op.drop_table("document_ingestion_jobs")
