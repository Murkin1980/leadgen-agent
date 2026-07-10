"""Add provider, qualification, and website check fields

Revision ID: 003
Revises: 002
Create Date: 2025-01-03 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "search_jobs",
        sa.Column("provider", sa.String(50), nullable=False, server_default="mock"),
    )
    op.add_column(
        "search_jobs",
        sa.Column("current_page", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "search_jobs",
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.add_column(
        "leads",
        sa.Column("provider", sa.String(50), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "website_check_status",
            sa.String(50),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "leads",
        sa.Column("qualification_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "leads",
        sa.Column("qualification_reasons", sa.Text(), nullable=True),
    )

    op.create_index("ix_search_jobs_provider", "search_jobs", ["provider"])
    op.create_index("ix_leads_provider", "leads", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_leads_provider")
    op.drop_index("ix_search_jobs_provider")
    op.drop_column("leads", "qualification_reasons")
    op.drop_column("leads", "qualification_score")
    op.drop_column("leads", "website_check_status")
    op.drop_column("leads", "provider")
    op.drop_column("search_jobs", "processed_count")
    op.drop_column("search_jobs", "current_page")
    op.drop_column("search_jobs", "provider")
