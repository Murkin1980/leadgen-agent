"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("slug", sa.String(500), nullable=True),
        sa.Column("category", sa.String(500), nullable=True),
        sa.Column("city", sa.String(200), nullable=True),
        sa.Column("address", sa.String(1000), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("whatsapp", sa.String(50), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("instagram", sa.String(500), nullable=True),
        sa.Column("telegram", sa.String(500), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("source_id", sa.String(200), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("reviews_count", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("has_website", sa.Boolean(), default=False),
        sa.Column("status", sa.String(50), default="collected"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source", "source_id", name="uq_lead_source"),
    )

    op.create_table(
        "search_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("city", sa.String(200), nullable=False),
        sa.Column("category", sa.String(500), nullable=False),
        sa.Column("limit", sa.Integer(), default=20),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("found_count", sa.Integer(), default=0),
        sa.Column("accepted_count", sa.Integer(), default=0),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "landing_pages",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("slug", sa.String(500), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("output_path", sa.String(1000), nullable=True),
        sa.Column("preview_url", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(50), default="draft"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("landing_pages")
    op.drop_table("search_jobs")
    op.drop_table("leads")
