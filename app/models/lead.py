import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LeadStatus(str, enum.Enum):
    collected = "collected"
    enriched = "enriched"
    generated = "generated"
    published = "published"
    rejected = "rejected"
    failed = "failed"


class WebsiteCheckStatus(str, enum.Enum):
    pending = "pending"
    ok = "ok"
    unreachable = "unreachable"
    has_website = "has_website"


class ConsentStatus(str, enum.Enum):
    unknown = "unknown"
    legitimate_interest_reviewed = "legitimate_interest_reviewed"
    consented = "consented"
    withdrawn = "withdrawn"
    blocked = "blocked"


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_lead_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("search_jobs.id"), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instagram: Mapped[str | None] = mapped_column(String(500), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_website: Mapped[bool] = mapped_column(default=False)
    website_check_status: Mapped[str] = mapped_column(String(50), default=WebsiteCheckStatus.pending.value)
    qualification_score: Mapped[int] = mapped_column(Integer, default=0)
    qualification_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=LeadStatus.collected.value)
    stage: Mapped[str] = mapped_column(String(50), default="new")
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(default=False)
    do_not_contact_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    contact_basis: Mapped[str | None] = mapped_column(String(100), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(50), default=ConsentStatus.unknown.value)
    consent_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    service_window_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job = relationship("SearchJob", back_populates="leads", foreign_keys=[search_job_id])
    landings = relationship("LandingPage", back_populates="lead", foreign_keys="LandingPage.lead_id")
    stage_history = relationship("LeadStageHistory", back_populates="lead", foreign_keys="LeadStageHistory.lead_id")
