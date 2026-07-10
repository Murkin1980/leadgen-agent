from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OutreachEvent(Base):
    __tablename__ = "outreach_events"

    id: Mapped[int] = mapped_column(String(50), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("outreach_messages.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    message = relationship("OutreachMessage", back_populates="events")
