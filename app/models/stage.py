import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LeadStage(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    landing_generated = "landing_generated"
    needs_review = "needs_review"
    ready_for_outreach = "ready_for_outreach"
    contacted = "contacted"
    replied = "replied"
    interested = "interested"
    proposal_sent = "proposal_sent"
    won = "won"
    lost = "lost"
    do_not_contact = "do_not_contact"


class LeadStageHistory(Base):
    __tablename__ = "lead_stage_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), nullable=False)
    from_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    lead = relationship("Lead", foreign_keys=[lead_id])
