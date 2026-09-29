"""Add unverified community product reports.

Revision ID: 20260928_12
Revises: 20260928_11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_12"
down_revision: str | None = "20260928_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("product_name", sa.String(length=300), nullable=True),
        sa.Column("product_name_key", sa.String(length=300), nullable=True),
        sa.Column("barcode", sa.String(length=14), nullable=True),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.String(length=2083), nullable=True),
        sa.Column("photo_mime_type", sa.String(length=30), nullable=True),
        sa.Column("photo_data", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "product_name IS NOT NULL OR barcode IS NOT NULL",
            name="ck_community_reports_product_identity",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'verified', 'rejected')",
            name="ck_community_reports_status",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_community_reports_product_id_products",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_community_reports"),
    )
    op.create_index("ix_community_reports_barcode", "community_reports", ["barcode"])
    op.create_index(
        "ix_community_reports_product_name_key",
        "community_reports",
        ["product_name_key"],
    )
    op.create_index("ix_community_reports_status", "community_reports", ["status"])
    op.create_table(
        "community_report_concerns",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("dimension", sa.String(length=50), nullable=False),
        sa.CheckConstraint(
            "dimension IN ('vegan_composition', 'environmental_impact', "
            "'women_workers', 'minority_inclusion')",
            name="ck_community_report_concerns_dimension",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["community_reports.id"],
            name="fk_community_report_concerns_report_id_community_reports",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "report_id",
            "dimension",
            name="pk_community_report_concerns",
        ),
    )


def downgrade() -> None:
    op.drop_table("community_report_concerns")
    op.drop_index("ix_community_reports_status", table_name="community_reports")
    op.drop_index("ix_community_reports_product_name_key", table_name="community_reports")
    op.drop_index("ix_community_reports_barcode", table_name="community_reports")
    op.drop_table("community_reports")
