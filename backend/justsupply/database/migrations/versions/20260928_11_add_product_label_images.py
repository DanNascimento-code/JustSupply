"""Store user-supplied product label evidence.

Revision ID: 20260928_11
Revises: 20260928_10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_11"
down_revision: str | None = "20260928_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_label_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=30), nullable=False),
        sa.Column("image_data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_label_images_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_label_images"),
    )
    op.create_index(
        "uq_product_label_images_product_sha256",
        "product_label_images",
        ["product_id", "sha256"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_product_label_images_product_sha256",
        table_name="product_label_images",
    )
    op.drop_table("product_label_images")
