"""Add report documents and unverified publication status.

Revision ID: 20260928_13
Revises: 20260928_12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_13"
down_revision: str | None = "20260928_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE community_reports SET status = 'published_unverified' "
        "WHERE status = 'verified'"
    )
    op.drop_constraint(
        "ck_community_reports_status",
        "community_reports",
        type_="check",
    )
    op.create_check_constraint(
        "ck_community_reports_status",
        "community_reports",
        "status IN ('pending_review', 'published_unverified', 'rejected')",
    )
    op.create_table(
        "community_report_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["community_reports.id"],
            name="fk_community_report_attachments_report_id_community_reports",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_community_report_attachments"),
    )
    op.create_index(
        "uq_community_report_attachments_report_sha256",
        "community_report_attachments",
        ["report_id", "sha256"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_community_report_attachments_report_sha256",
        table_name="community_report_attachments",
    )
    op.drop_table("community_report_attachments")
    op.execute(
        "UPDATE community_reports SET status = 'verified' "
        "WHERE status = 'published_unverified'"
    )
    op.drop_constraint(
        "ck_community_reports_status",
        "community_reports",
        type_="check",
    )
    op.create_check_constraint(
        "ck_community_reports_status",
        "community_reports",
        "status IN ('pending_review', 'verified', 'rejected')",
    )
