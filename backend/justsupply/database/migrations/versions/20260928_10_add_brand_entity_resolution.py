"""Add resolved legal-entity metadata to brands.

Revision ID: 20260928_10
Revises: 20260928_09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_10"
down_revision: str | None = "20260928_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("legal_name", sa.String(length=300), nullable=True))
    op.add_column("brands", sa.Column("parent_company", sa.String(length=300), nullable=True))
    op.add_column("brands", sa.Column("jurisdiction", sa.String(length=200), nullable=True))
    op.add_column(
        "brands",
        sa.Column("resolution_source_url", sa.String(length=2083), nullable=True),
    )
    op.add_column("brands", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("brands", "resolved_at")
    op.drop_column("brands", "resolution_source_url")
    op.drop_column("brands", "jurisdiction")
    op.drop_column("brands", "parent_company")
    op.drop_column("brands", "legal_name")
