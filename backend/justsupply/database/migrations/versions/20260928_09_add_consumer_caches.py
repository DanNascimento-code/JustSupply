"""Add catalog-search and grounded-answer caches.

Revision ID: 20260928_09
Revises: 20260925_08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260928_09"
down_revision: str | None = "20260925_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_search_cache",
        sa.Column("query_key", sa.String(length=64), nullable=False),
        sa.Column("query_text", sa.String(length=120), nullable=False),
        sa.Column("query_type", sa.String(length=20), nullable=False),
        sa.Column("products", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("query_key", name="pk_catalog_search_cache"),
    )
    op.create_table(
        "consumer_answer_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("research_run_id", sa.Uuid(), nullable=False),
        sa.Column("question_key", sa.String(length=64), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["ai_research_runs.id"],
            name="fk_consumer_answer_cache_research_run_id_ai_research_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_consumer_answer_cache"),
    )
    op.create_index(
        "uq_consumer_answer_cache_lookup",
        "consumer_answer_cache",
        ["research_run_id", "question_key", "language", "top_k"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_consumer_answer_cache_lookup", table_name="consumer_answer_cache")
    op.drop_table("consumer_answer_cache")
    op.drop_table("catalog_search_cache")
