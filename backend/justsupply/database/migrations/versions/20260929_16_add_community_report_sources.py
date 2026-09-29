"""Allow multiple source links on community reports.

Revision ID: 20260929_16
Revises: 20260928_15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260929_16"
down_revision: str | None = "20260928_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_report_sources",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2083), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["community_reports.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("report_id", "url"),
    )
    op.execute(
        "INSERT INTO community_report_sources (report_id, url, created_at) "
        "SELECT id, evidence_url, created_at FROM community_reports "
        "WHERE evidence_url IS NOT NULL"
    )
    op.drop_column("community_reports", "evidence_url")


def downgrade() -> None:
    op.add_column(
        "community_reports",
        sa.Column("evidence_url", sa.String(length=2083), nullable=True),
    )
    op.execute(
        "UPDATE community_reports AS reports SET evidence_url = ("
        "SELECT sources.url FROM community_report_sources AS sources "
        "WHERE sources.report_id = reports.id "
        "ORDER BY sources.created_at, sources.url LIMIT 1)"
    )
    op.drop_table("community_report_sources")
