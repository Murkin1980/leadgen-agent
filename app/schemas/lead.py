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
    provider: str | None = None
    website_check_status: str = "pending"
    qualification_score: int = 0
    qualification_reasons: str | None = None
    status: str
    stage: str = "new"
    assigned_to: str | None = None
    last_contacted_at: datetime | None = None
    next_follow_up_at: datetime | None = None
    do_not_contact: bool = False
    do_not_contact_reason: str | None = None
    preferred_channel: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
