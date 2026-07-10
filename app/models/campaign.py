import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    ready = "ready"
    running = "running"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class OutreachChannel(str, enum.Enum):
    whatsapp = "whatsapp"
    email = "email"
    telegram = "telegram"
    sms = "sms"


class OutreachCampaign(Base):
    __tablename__ = "outreach_campaigns"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=CampaignStatus.draft.value
    )
    language: Mapped[str] = mapped_column(String(10), default="ru")
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages = relationship(
        "OutreachMessage",
        back_populates="campaign",
        order_by="OutreachMessage.created_at.desc()",
    )


class MessageStatus(str, enum.Enum):
    draft = "draft"
    needs_review = "needs_review"
    approved = "approved"
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    replied = "replied"
    failed = "failed"
    cancelled = "cancelled"
    blocked = "blocked"


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    __table_args__ = (
        UniqueConstraint(
            "lead_id", "channel", "campaign_id",
            name="uq_outreach_first_contact",
        ),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("outreach_campaigns.id"), nullable=False
    )
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=MessageStatus.draft.value
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_number: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    campaign = relationship("OutreachCampaign", back_populates="messages")
    lead = relationship("Lead", foreign_keys=[lead_id])
    events = relationship(
        "OutreachEvent",
        back_populates="message",
        order_by="OutreachEvent.created_at.desc()",
    )
