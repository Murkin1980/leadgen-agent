from datetime import datetime

from pydantic import BaseModel


class LeadResponse(BaseModel):
    id: int
    name: str
    slug: str | None = None
    category: str | None = None
    city: str | None = None
    address: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    website: str | None = None
    instagram: str | None = None
    telegram: str | None = None
    source: str | None = None
    source_id: str | None = None
    source_url: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    has_website: bool = False
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
