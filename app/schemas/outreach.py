from datetime import datetime
from pydantic import BaseModel


class CampaignCreate(BaseModel):
    name: str
    channel: str
    language: str = "ru"


class CampaignResponse(BaseModel):
    id: str
    name: str
    channel: str
    status: str
    language: str
    created_by: str | None = None
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class CampaignAddLeads(BaseModel):
    lead_ids: list[int]


class MessageResponse(BaseModel):
    id: str
    campaign_id: str
    lead_id: int
    channel: str
    recipient: str
    subject: str | None = None
    body: str
    status: str
    provider_message_id: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    replied_at: datetime | None = None
    failed_at: datetime | None = None
    error_message: str | None = None
    follow_up_number: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class MessageApproveRequest(BaseModel):
    approved_by: str = "admin"


class MessageRejectRequest(BaseModel):
    reason: str = "Rejected"


class MessageUpdateRequest(BaseModel):
    subject: str | None = None
    body: str | None = None


class OutreachMetricsResponse(BaseModel):
    draft_count: int
    approved_count: int
    sent_count: int
    delivered_count: int
    replied_count: int
    failed_count: int
    opt_out_count: int
    reply_rate: float
    conversion_by_stage: dict[str, int]


class FollowUpCandidateResponse(BaseModel):
    message_id: str
    lead_id: int
    lead_name: str
    channel: str
    follow_up_number: int
    last_sent_at: datetime | None = None


class StageChangeRequest(BaseModel):
    to_stage: str
    reason: str | None = None
    changed_by: str | None = "admin"


class StageHistoryResponse(BaseModel):
    id: int
    lead_id: int
    from_stage: str | None = None
    to_stage: str
    changed_by: str | None = None
    reason: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: str
    actor: str | None = None
    details_json: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True
