"""006 WhatsApp production operations

Revision ID: 006
Revises: 005
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, column in [
        ("contact_basis", sa.Column("contact_basis", sa.String(100), nullable=True)),
        ("consent_status", sa.Column("consent_status", sa.String(50), nullable=False, server_default="unknown")),
        ("consent_source", sa.Column("consent_source", sa.String(500), nullable=True)),
        ("consent_recorded_at", sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True)),
        ("consent_notes", sa.Column("consent_notes", sa.Text(), nullable=True)),
        ("last_inbound_at", sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True)),
        ("service_window_expires_at", sa.Column("service_window_expires_at", sa.DateTime(timezone=True), nullable=True)),
        ("last_outbound_at", sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True)),
    ]:
        op.add_column("leads", column)

    op.add_column("outreach_messages", sa.Column("template_name", sa.String(200), nullable=True))
    op.add_column("outreach_messages", sa.Column("template_language", sa.String(20), nullable=True))
    op.add_column("outreach_messages", sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("outreach_messages", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.add_column("outreach_messages", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("outreach_messages", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outreach_messages", sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_unique_constraint("uq_outreach_message_idempotency", "outreach_messages", ["idempotency_key"])

    op.create_table(
        "whatsapp_templates",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("language_code", sa.String(20), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("header_type", sa.String(50), nullable=True),
        sa.Column("footer_text", sa.Text(), nullable=True),
        sa.Column("button_schema_json", sa.Text(), nullable=True),
        sa.Column("provider_template_id", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", "language_code", name="uq_whatsapp_template_name_language"),
    )

    op.create_table(
        "inbound_messages",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="whatsapp"),
        sa.Column("provider_message_id", sa.String(200), nullable=False, unique=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("from_phone", sa.String(50), nullable=False),
        sa.Column("message_type", sa.String(50), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("media_id", sa.String(200), nullable=True),
        sa.Column("raw_metadata_json", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="new"),
    )
    op.create_index("ix_inbound_messages_lead_id", "inbound_messages", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_inbound_messages_lead_id", table_name="inbound_messages")
    op.drop_table("inbound_messages")
    op.drop_table("whatsapp_templates")
    op.drop_constraint("uq_outreach_message_idempotency", "outreach_messages", type_="unique")
    for column in ["retryable", "next_retry_at", "attempt_count", "idempotency_key", "is_template", "template_language", "template_name"]:
        op.drop_column("outreach_messages", column)
    for column in ["last_outbound_at", "service_window_expires_at", "last_inbound_at", "consent_notes", "consent_recorded_at", "consent_source", "consent_status", "contact_basis"]:
        op.drop_column("leads", column)
