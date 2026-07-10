from datetime import datetime

from pydantic import BaseModel


class JobCreate(BaseModel):
    city: str
    category: str
    limit: int = 20
    provider: str = "mock"


class JobResponse(BaseModel):
    id: int
    status: str
    city: str
    category: str
    limit: int
    provider: str
    found_count: int
    accepted_count: int
    current_page: int = 0
    processed_count: int = 0
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True
