"""Add positive and negative outcomes to community assessments.

Revision ID: 20260928_14
Revises: 20260928_13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_14"
down_revision: str | None = "20260928_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("community_report_concerns", "community_report_assessments")
    op.drop_constraint(
        "ck_community_report_concerns_dimension",
        "community_report_assessments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_community_report_assessments_dimension",
        "community_report_assessments",
        "dimension IN ('vegan_composition', 'environmental_impact', "
        "'women_workers', 'minority_inclusion')",
    )
    op.add_column(
        "community_report_assessments",
        sa.Column(
            "outcome",
            sa.String(length=10),
            nullable=False,
            server_default="negative",
        ),
    )
    op.create_check_constraint(
        "ck_community_report_assessments_outcome",
        "community_report_assessments",
        "outcome IN ('positive', 'negative')",
    )
    op.alter_column(
        "community_report_assessments",
        "outcome",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_community_report_assessments_outcome",
        "community_report_assessments",
        type_="check",
    )
    op.drop_column("community_report_assessments", "outcome")
    op.drop_constraint(
        "ck_community_report_assessments_dimension",
        "community_report_assessments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_community_report_concerns_dimension",
        "community_report_assessments",
        "dimension IN ('vegan_composition', 'environmental_impact', "
        "'women_workers', 'minority_inclusion')",
    )
    op.rename_table("community_report_assessments", "community_report_concerns")
