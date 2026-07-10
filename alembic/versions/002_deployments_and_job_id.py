"""Add deployments table and search_job_id to leads

Revision ID: 002
Revises: 001
Create Date: 2025-01-02 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("search_job_id", sa.Integer(), sa.ForeignKey("search_jobs.id"), nullable=True),
    )
    op.create_index("ix_leads_search_job_id", "leads", ["search_job_id"])

    op.create_table(
        "deployments",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("search_jobs.id"), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), default="queued"),
        sa.Column("project_name", sa.String(200), nullable=True),
        sa.Column("branch", sa.String(100), nullable=True),
        sa.Column("deployment_url", sa.String(1000), nullable=True),
        sa.Column("provider_deployment_id", sa.String(200), nullable=True),
        sa.Column("stdout_excerpt", sa.Text(), nullable=True),
        sa.Column("stderr_excerpt", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deployments_job_id", "deployments", ["job_id"])
    op.create_index("ix_deployments_status", "deployments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_deployments_status")
    op.drop_index("ix_deployments_job_id")
    op.drop_table("deployments")
    op.drop_index("ix_leads_search_job_id")
    op.drop_column("leads", "search_job_id")
