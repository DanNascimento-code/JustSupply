"""Add the human review workflow to claims.

Revision ID: 20260915_03
Revises: 20260915_02
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_03"
down_revision: str | Sequence[str] | None = "20260915_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column(
            "origin",
            sa.String(length=20),
            server_default="catalog",
            nullable=False,
        ),
    )
    op.add_column(
        "claims",
        sa.Column(
            "review_status",
            sa.String(length=20),
            server_default="not_required",
            nullable=False,
        ),
    )
    op.add_column(
        "claims",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_claims_origin",
        "claims",
        "origin IN ('catalog', 'manual')",
    )
    op.create_check_constraint(
        "ck_claims_review_status",
        "claims",
        "review_status IN ('not_required', 'pending', 'approved', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_claims_review_status", "claims", type_="check")
    op.drop_constraint("ck_claims_origin", "claims", type_="check")
    op.drop_column("claims", "reviewed_at")
    op.drop_column("claims", "review_status")
    op.drop_column("claims", "origin")
