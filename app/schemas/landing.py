from datetime import datetime

from pydantic import BaseModel


class LandingResponse(BaseModel):
    id: str
    lead_id: int
    slug: str
    title: str | None = None
    preview_url: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
