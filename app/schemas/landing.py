from datetime import datetime

from pydantic import BaseModel


class LandingResponse(BaseModel):
    id: str
    lead_id: int
    slug: str
    title: str | None = None
    preview_url: str | None = None
    status: str
    review_status: str = "draft"
    review_note: str | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None
    current_version: int = 0
    generation_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class LandingVersionResponse(BaseModel):
    id: str
    landing_page_id: str
    version_number: int
    profile_json: str | None = None
    html_snapshot_path: str | None = None
    change_source: str
    change_note: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class LandingApproveRequest(BaseModel):
    approved_by: str = "admin"


class LandingRejectRequest(BaseModel):
    reason: str = "Не прошло проверку"
