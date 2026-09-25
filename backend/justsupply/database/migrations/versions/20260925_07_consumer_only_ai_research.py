"""Replace Pro workflows with consumer AI research.

Revision ID: 20260925_07
Revises: 20260923_06
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "20260925_07"
down_revision: str | Sequence[str] | None = "20260923_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("document_ingestion_jobs")
    op.drop_table("document_chunks")
    op.drop_table("ai_findings")
    op.drop_table("ai_extraction_runs")
    op.drop_table("source_documents")
    op.drop_table("suppliers")

    op.execute("DELETE FROM claims WHERE origin = 'manual'")
    op.drop_constraint("ck_claims_review_status", "claims", type_="check")
    op.drop_constraint("ck_claims_origin", "claims", type_="check")
    op.drop_column("claims", "reviewed_at")
    op.drop_column("claims", "review_status")
    op.add_column("claims", sa.Column("limitations", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_claims_origin",
        "claims",
        "origin IN ('catalog', 'ai_research')",
    )

    op.create_table(
        "ai_research_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("provider_response_id", sa.String(length=200), nullable=True),
        sa.Column("searched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_research_runs_product_id",
        "ai_research_runs",
        ["product_id"],
    )

    op.add_column("evidence_records", sa.Column("research_run_id", sa.Uuid(), nullable=True))
    op.add_column(
        "evidence_records",
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "evidence_records",
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
    )
    op.add_column("evidence_records", sa.Column("embedding", VECTOR(1536), nullable=True))
    op.create_foreign_key(
        "fk_evidence_records_research_run_id",
        "evidence_records",
        "ai_research_runs",
        ["research_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_evidence_records_research_run_id",
        "evidence_records",
        ["research_run_id"],
    )
    op.create_index(
        "ix_evidence_records_embedding_hnsw",
        "evidence_records",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    raise NotImplementedError(
        "This destructive product-scope migration cannot restore removed Pro data."
    )
