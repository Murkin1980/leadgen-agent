"""005 CRM pipeline, outreach campaigns, messages, events, audit log

Revision ID: 005
Revises: 004
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("stage", sa.String(50), server_default="new"))
    op.add_column("leads", sa.Column("assigned_to", sa.String(100), nullable=True))
    op.add_column("leads", sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("do_not_contact", sa.Boolean(), server_default=sa.text("false")))
    op.add_column("leads", sa.Column("do_not_contact_reason", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("preferred_channel", sa.String(50), nullable=True))
    op.add_column("leads", sa.Column("notes", sa.Text(), nullable=True))

    op.create_table(
        "lead_stage_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("from_stage", sa.String(50), nullable=True),
        sa.Column("to_stage", sa.String(50), nullable=False),
        sa.Column("changed_by", sa.String(100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "outreach_campaigns",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("language", sa.String(10), server_default="ru"),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "outreach_messages",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("campaign_id", sa.String(50), sa.ForeignKey("outreach_campaigns.id"), nullable=False),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("recipient", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("provider_message_id", sa.String(200), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("follow_up_number", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_outreach_first_contact",
        "outreach_messages",
        ["lead_id", "channel", "campaign_id"],
    )

    op.create_table(
        "outreach_events",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("message_id", sa.String(50), sa.ForeignKey("outreach_messages.id"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("provider_event_id", sa.String(200), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(100), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("outreach_events")
    op.drop_constraint("uq_outreach_first_contact", "outreach_messages", type_="unique")
    op.drop_table("outreach_messages")
    op.drop_table("outreach_campaigns")
    op.drop_table("lead_stage_history")
    op.drop_column("leads", "notes")
    op.drop_column("leads", "preferred_channel")
    op.drop_column("leads", "do_not_contact_reason")
    op.drop_column("leads", "do_not_contact")
    op.drop_column("leads", "next_follow_up_at")
    op.drop_column("leads", "last_contacted_at")
    op.drop_column("leads", "assigned_to")
    op.drop_column("leads", "stage")
