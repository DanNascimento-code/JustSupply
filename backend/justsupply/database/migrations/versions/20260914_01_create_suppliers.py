"""Create the suppliers table.

Revision ID: 20260914_01
Revises:
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("legal_name_key", sa.String(length=400), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("website", sa.String(length=2083), nullable=True),
        sa.Column(
            "commodities",
            postgresql.ARRAY(sa.String(length=50)),
            nullable=False,
        ),
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
            "country_code ~ '^[A-Z]{2}$'",
            name="ck_suppliers_country_code_format",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_suppliers"),
        sa.UniqueConstraint("legal_name_key", name="uq_suppliers_legal_name_key"),
    )


def downgrade() -> None:
    op.drop_table("suppliers")
    op.execute("DROP EXTENSION IF EXISTS vector")
