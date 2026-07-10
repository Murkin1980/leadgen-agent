import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WhatsAppTemplateStatus(str, enum.Enum):
    draft = "draft"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    disabled = "disabled"


class WhatsAppTemplate(Base):
    __tablename__ = "whatsapp_templates"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    language_code: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=WhatsAppTemplateStatus.draft.value)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    header_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    button_schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_template_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class InboundMessageStatus(str, enum.Enum):
    new = "new"
    handled = "handled"
    ignored = "ignored"


class InboundMessage(Base):
    __tablename__ = "inbound_messages"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), default="whatsapp")
    provider_message_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    from_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=InboundMessageStatus.new.value)

    lead = relationship("Lead", foreign_keys=[lead_id])
