from datetime import datetime
from pydantic import BaseModel


class DeploymentResponse(BaseModel):
    id: str
    job_id: int | None = None
    provider: str
    status: str
    project_name: str | None = None
    branch: str | None = None
    deployment_url: str | None = None
    provider_deployment_id: str | None = None
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True
