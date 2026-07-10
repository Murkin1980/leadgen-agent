import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeploymentStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("search_jobs.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=DeploymentStatus.queued.value
    )
    project_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    deployment_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    provider_deployment_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    stdout_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
