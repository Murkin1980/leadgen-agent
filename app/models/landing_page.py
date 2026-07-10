import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LandingStatus(str, enum.Enum):
    draft = "draft"
    needs_review = "needs_review"
    approved = "approved"
    rejected = "rejected"
    published = "published"
    deployed = "deployed"
    failed = "failed"


class ReviewStatus(str, enum.Enum):
    draft = "draft"
    needs_review = "needs_review"
    approved = "approved"
    rejected = "rejected"
    published = "published"


class LandingPage(Base):
    __tablename__ = "landing_pages"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default=LandingStatus.draft.value
    )
    review_status: Mapped[str] = mapped_column(
        String(50), default=ReviewStatus.draft.value
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    generation_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("content_generations.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lead = relationship("Lead", back_populates="landings", foreign_keys=[lead_id])
    versions = relationship(
        "LandingPageVersion",
        back_populates="landing_page",
        order_by="LandingPageVersion.version_number.desc()",
    )


class ChangeSource(str, enum.Enum):
    template = "template"
    openai = "openai"
    manual = "manual"
    regeneration = "regeneration"


class LandingPageVersion(Base):
    __tablename__ = "landing_page_versions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    landing_page_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("landing_pages.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_snapshot_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    change_source: Mapped[str] = mapped_column(String(50), nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    landing_page = relationship("LandingPage", back_populates="versions")
