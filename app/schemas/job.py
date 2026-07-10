from datetime import datetime

from pydantic import BaseModel


class JobCreate(BaseModel):
    city: str
    category: str
    limit: int = 20


class JobResponse(BaseModel):
    id: int
    status: str
    city: str
    category: str
    limit: int
    found_count: int
    accepted_count: int
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True
