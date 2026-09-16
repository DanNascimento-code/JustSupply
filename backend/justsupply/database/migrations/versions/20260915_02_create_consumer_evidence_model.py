"""Create the consumer product and evidence model.

Revision ID: 20260915_02
Revises: 20260914_01
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_02"
down_revision: str | Sequence[str] | None = "20260914_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_key", sa.String(length=400), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_brands"),
        sa.UniqueConstraint("name_key", name="uq_brands_name_key"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("image_url", sa.String(length=2083), nullable=True),
        sa.Column("catalog_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brands.id"],
            name="fk_products_brand_id_brands",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("barcode", name="uq_products_barcode"),
    )
    op.create_table(
        "evidence_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url", sa.String(length=2083), nullable=False),
        sa.Column("url_key", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_sources"),
        sa.UniqueConstraint("url_key", name="uq_evidence_sources_url_key"),
    )
    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_scope", sa.String(length=20), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("dimension", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(subject_scope = 'product' AND product_id IS NOT NULL AND brand_id IS NULL) "
            "OR (subject_scope = 'brand' AND brand_id IS NOT NULL AND product_id IS NULL)",
            name="ck_claims_exactly_one_subject",
        ),
        sa.CheckConstraint(
            "status IN ('supported', 'mixed', 'concern', 'not_disclosed', 'unknown')",
            name="ck_claims_status",
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brands.id"],
            name="fk_claims_brand_id_brands",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_claims_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claims"),
    )
    op.create_index(
        "uq_claims_product_dimension",
        "claims",
        ["product_id", "dimension"],
        unique=True,
        postgresql_where=sa.text("product_id IS NOT NULL"),
    )
    op.create_index(
        "uq_claims_brand_dimension",
        "claims",
        ["brand_id", "dimension"],
        unique=True,
        postgresql_where=sa.text("brand_id IS NOT NULL"),
    )
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("source_location", sa.String(length=500), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["evidence_sources.id"],
            name="fk_evidence_records_source_id_evidence_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_records"),
    )
    op.create_index(
        "uq_evidence_records_source_fingerprint",
        "evidence_records",
        ["source_id", "fingerprint"],
        unique=True,
    )
    op.create_table(
        "claim_evidence_records",
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_record_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "relationship IN ('supports', 'contradicts', 'context')",
            name="ck_claim_evidence_records_relationship",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            name="fk_claim_evidence_records_claim_id_claims",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_record_id"],
            ["evidence_records.id"],
            name="fk_claim_evidence_records_evidence_record_id_evidence_records",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "claim_id",
            "evidence_record_id",
            name="pk_claim_evidence_records",
        ),
    )


def downgrade() -> None:
    op.drop_table("claim_evidence_records")
    op.drop_index(
        "uq_evidence_records_source_fingerprint",
        table_name="evidence_records",
    )
    op.drop_table("evidence_records")
    op.drop_index("uq_claims_brand_dimension", table_name="claims")
    op.drop_index("uq_claims_product_dimension", table_name="claims")
    op.drop_table("claims")
    op.drop_table("evidence_sources")
    op.drop_table("products")
    op.drop_table("brands")
