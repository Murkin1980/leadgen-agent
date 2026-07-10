"""Add content generations, landing versions, review workflow

Revision ID: 004
Revises: 003
Create Date: 2025-01-10 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_generations",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column(
            "landing_page_id",
            sa.String(50),
            sa.ForeignKey("landing_pages.id"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column(
            "status", sa.String(50), nullable=False, server_default="queued"
        ),
        sa.Column("input_snapshot_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("validation_errors_json", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("language", sa.String(10), nullable=False, server_default="ru"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_content_generations_lead_id", "content_generations", ["lead_id"]
    )
    op.create_index(
        "ix_content_generations_status", "content_generations", ["status"]
    )

    op.add_column(
        "landing_pages",
        sa.Column(
            "review_status", sa.String(50), nullable=False, server_default="draft"
        ),
    )
    op.add_column("landing_pages", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column(
        "landing_pages",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "landing_pages", sa.Column("approved_by", sa.String(100), nullable=True)
    )
    op.add_column(
        "landing_pages",
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "landing_pages",
        sa.Column(
            "generation_id",
            sa.String(50),
            sa.ForeignKey("content_generations.id"),
            nullable=True,
        ),
    )

    op.create_table(
        "landing_page_versions",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column(
            "landing_page_id",
            sa.String(50),
            sa.ForeignKey("landing_pages.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("html_snapshot_path", sa.String(1000), nullable=True),
        sa.Column("change_source", sa.String(50), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_landing_page_versions_lp_id",
        "landing_page_versions",
        ["landing_page_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_landing_page_versions_lp_id")
    op.drop_table("landing_page_versions")

    op.drop_column("landing_pages", "generation_id")
    op.drop_column("landing_pages", "current_version")
    op.drop_column("landing_pages", "approved_by")
    op.drop_column("landing_pages", "approved_at")
    op.drop_column("landing_pages", "review_note")
    op.drop_column("landing_pages", "review_status")

    op.drop_index("ix_content_generations_status")
    op.drop_index("ix_content_generations_lead_id")
    op.drop_table("content_generations")
