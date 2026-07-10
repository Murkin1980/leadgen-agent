from datetime import datetime

from pydantic import BaseModel


class ContentGenerationCreate(BaseModel):
    language: str = "ru"
    provider: str | None = None
    notes: str | None = None


class ContentGenerationResponse(BaseModel):
    id: str
    lead_id: int
    landing_page_id: str | None = None
    provider: str
    model: str | None = None
    prompt_version: str
    status: str
    input_snapshot_json: str | None = None
    output_json: str | None = None
    validation_errors_json: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    error_message: str | None = None
    language: str = "ru"
    notes: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True
