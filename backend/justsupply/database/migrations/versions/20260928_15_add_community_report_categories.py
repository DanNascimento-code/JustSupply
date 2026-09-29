"""Add normalized food categories to community reports.

Revision ID: 20260928_15
Revises: 20260928_14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_15"
down_revision: str | None = "20260928_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = (
    "'baby_food', 'bakery', 'beverages', 'biscuits_cookies', "
    "'breakfast_cereals', 'candy', 'chocolate', 'coffee_tea', "
    "'condiments_sauces', 'dairy', 'dairy_alternatives', 'desserts', "
    "'frozen_foods', 'ice_cream', 'meat_alternatives', 'pasta_noodles', "
    "'ready_meals', 'snacks_chips', 'spreads', 'yogurt', 'other'"
)


def upgrade() -> None:
    op.add_column(
        "community_reports",
        sa.Column(
            "category",
            sa.String(length=50),
            nullable=False,
            server_default="other",
        ),
    )
    op.create_check_constraint(
        "ck_community_reports_category",
        "community_reports",
        f"category IN ({CATEGORIES})",
    )
    op.create_index(
        "ix_community_reports_category",
        "community_reports",
        ["category"],
    )
    op.alter_column("community_reports", "category", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_community_reports_category", table_name="community_reports")
    op.drop_constraint(
        "ck_community_reports_category",
        "community_reports",
        type_="check",
    )
    op.drop_column("community_reports", "category")
