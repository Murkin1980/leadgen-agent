import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.audit import AuditLog
from app.models.campaign import (
    OutreachCampaign,
    OutreachMessage,
    CampaignStatus,
    MessageStatus,
)
from app.models.event import OutreachEvent
from app.models.lead import Lead
from app.models.landing_page import LandingPage, LandingStatus, ReviewStatus
from app.models.stage import LeadStage, LeadStageHistory
from app.outreach.message_generator import MessageContext, generate_messages
from app.outreach.service import get_follow_up_candidates, get_outreach_metrics
from app.outreach.stage_service import transition_lead_stage, VALID_TRANSITIONS
from app.security import log_audit_event
from app.schemas.outreach import (
    AuditLogResponse,
    CampaignAddLeads,
    CampaignCreate,
    CampaignResponse,
    FollowUpCandidateResponse,
    MessageApproveRequest,
    MessageRejectRequest,
    MessageResponse,
    MessageUpdateRequest,
    OutreachMetricsResponse,
    StageChangeRequest,
    StageHistoryResponse,
)
from app.schemas.lead import LeadResponse
from app.workers.connection import redis_conn

router = APIRouter()
logger = logging.getLogger(__name__)


# --- Campaigns ---

@router.post("/campaigns", response_model=CampaignResponse)
def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
):
    campaign = OutreachCampaign(
        id=str(uuid.uuid4())[:12],
        name=payload.name,
        channel=payload.channel,
        language=payload.language,
        status=CampaignStatus.draft.value,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(OutreachCampaign)
    if status:
        q = q.filter(OutreachCampaign.status == status)
    return q.order_by(OutreachCampaign.created_at.desc()).limit(limit).all()


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = db.query(OutreachCampaign).filter(
        OutreachCampaign.id == campaign_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/campaigns/{campaign_id}/add-leads")
def add_leads_to_campaign(
    campaign_id: str,
    payload: CampaignAddLeads,
    db: Session = Depends(get_db),
):
    campaign = db.query(OutreachCampaign).filter(
        OutreachCampaign.id == campaign_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    added = 0
    for lead_id in payload.lead_ids:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead or lead.do_not_contact:
            continue

        existing = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.lead_id == lead_id,
                OutreachMessage.campaign_id == campaign_id,
            )
            .first()
        )
        if existing:
            continue

        msg = OutreachMessage(
            id=str(uuid.uuid4())[:12],
            campaign_id=campaign_id,
            lead_id=lead_id,
            channel=campaign.channel,
            recipient="",
            body="",
            status=MessageStatus.draft.value,
        )
        db.add(msg)
        added += 1

    db.commit()
    return {"added": added}


@router.post("/campaigns/{campaign_id}/generate-messages")
def generate_messages_for_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    from rq import Queue
    campaign = db.query(OutreachCampaign).filter(
        OutreachCampaign.id == campaign_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    q = Queue("outreach_generate", connection=redis_conn)
    q.enqueue("app.workers.outreach_generator_worker.run_outreach_generator", campaign_id)
    return {"status": "queued"}


@router.get("/campaigns/{campaign_id}/messages", response_model=list[MessageResponse])
def list_campaign_messages(
    campaign_id: str,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(OutreachMessage).filter(
        OutreachMessage.campaign_id == campaign_id
    )
    if status:
        q = q.filter(OutreachMessage.status == status)
    return q.order_by(OutreachMessage.created_at.desc()).all()


@router.post("/campaigns/{campaign_id}/send-approved")
def send_approved_messages(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    from rq import Queue
    campaign = db.query(OutreachCampaign).filter(
        OutreachCampaign.id == campaign_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if not settings.outreach_enabled:
        raise HTTPException(status_code=400, detail="Outreach is disabled")

    messages = (
        db.query(OutreachMessage)
        .filter(
            OutreachMessage.campaign_id == campaign_id,
            OutreachMessage.status == MessageStatus.approved.value,
        )
        .all()
    )
    if not messages:
        raise HTTPException(status_code=400, detail="No approved messages to send")

    q = Queue("outreach_send", connection=redis_conn)
    for msg in messages:
        q.enqueue("app.workers.outreach_sender_worker.run_outreach_sender", msg.id)
    return {"queued": len(messages)}


@router.post("/campaigns/{campaign_id}/pause", response_model=CampaignResponse)
def pause_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = db.query(OutreachCampaign).filter(
        OutreachCampaign.id == campaign_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in (CampaignStatus.running.value, CampaignStatus.ready.value):
        raise HTTPException(status_code=400, detail=f"Cannot pause campaign in status: {campaign.status}")
    campaign.status = CampaignStatus.paused.value
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/campaigns/{campaign_id}/resume", response_model=CampaignResponse)
def resume_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = db.query(OutreachCampaign).filter(
        OutreachCampaign.id == campaign_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != CampaignStatus.paused.value:
        raise HTTPException(status_code=400, detail=f"Cannot resume campaign in status: {campaign.status}")
    campaign.status = CampaignStatus.running.value
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignResponse)
def cancel_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = db.query(OutreachCampaign).filter(
        OutreachCampaign.id == campaign_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status in (CampaignStatus.completed.value, CampaignStatus.cancelled.value):
        raise HTTPException(status_code=400, detail=f"Cannot cancel campaign in status: {campaign.status}")
    campaign.status = CampaignStatus.cancelled.value
    db.commit()
    db.refresh(campaign)
    return campaign


# --- Messages ---

@router.get("/outreach-messages", response_model=list[MessageResponse])
def list_messages(
    campaign_id: str | None = None,
    lead_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(OutreachMessage)
    if campaign_id:
        q = q.filter(OutreachMessage.campaign_id == campaign_id)
    if lead_id:
        q = q.filter(OutreachMessage.lead_id == lead_id)
    if status:
        q = q.filter(OutreachMessage.status == status)
    return q.order_by(OutreachMessage.created_at.desc()).limit(limit).all()


@router.get("/outreach-messages/{message_id}", response_model=MessageResponse)
def get_message(message_id: str, db: Session = Depends(get_db)):
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@router.post("/outreach-messages/{message_id}/approve", response_model=MessageResponse)
def approve_message(
    message_id: str,
    payload: MessageApproveRequest | None = None,
    db: Session = Depends(get_db),
):
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status != MessageStatus.needs_review.value:
        raise HTTPException(status_code=400, detail=f"Cannot approve message in status: {msg.status}")

    msg.status = MessageStatus.approved.value
    msg.approved_by = (payload.approved_by if payload else "admin") or "admin"
    msg.approved_at = datetime.now(timezone.utc)
    log_audit_event(
        db, "message_approved", "outreach_message", message_id,
        actor=msg.approved_by,
    )
    db.commit()
    db.refresh(msg)
    return msg


@router.post("/outreach-messages/{message_id}/reject", response_model=MessageResponse)
def reject_message(
    message_id: str,
    payload: MessageRejectRequest | None = None,
    db: Session = Depends(get_db),
):
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status not in (MessageStatus.needs_review.value, MessageStatus.draft.value):
        raise HTTPException(status_code=400, detail=f"Cannot reject message in status: {msg.status}")

    msg.status = MessageStatus.cancelled.value
    msg.error_message = (payload.reason if payload else "Rejected") or "Rejected"
    log_audit_event(
        db, "message_rejected", "outreach_message", message_id,
        actor="admin",
    )
    db.commit()
    db.refresh(msg)
    return msg


@router.put("/outreach-messages/{message_id}", response_model=MessageResponse)
def update_message(
    message_id: str,
    payload: MessageUpdateRequest,
    db: Session = Depends(get_db),
):
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status not in (MessageStatus.draft.value, MessageStatus.needs_review.value):
        raise HTTPException(status_code=400, detail=f"Cannot edit message in status: {msg.status}")

    if payload.subject is not None:
        msg.subject = payload.subject
    if payload.body is not None:
        msg.body = payload.body
    msg.status = MessageStatus.needs_review.value
    db.commit()
    db.refresh(msg)
    return msg


@router.post("/outreach-messages/{message_id}/send", response_model=MessageResponse)
def send_message(
    message_id: str,
    db: Session = Depends(get_db),
):
    from rq import Queue
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status != MessageStatus.approved.value:
        raise HTTPException(status_code=400, detail=f"Cannot send message in status: {msg.status}")
    if not settings.outreach_enabled:
        raise HTTPException(status_code=400, detail="Outreach is disabled")

    msg.status = MessageStatus.queued.value
    db.commit()

    q = Queue("outreach_send", connection=redis_conn)
    q.enqueue("app.workers.outreach_sender_worker.run_outreach_sender", message_id)
    db.refresh(msg)
    return msg


# --- Lead CRM ---

@router.post("/leads/{lead_id}/stage", response_model=LeadResponse)
def change_lead_stage(
    lead_id: int,
    payload: StageChangeRequest,
    db: Session = Depends(get_db),
):
    try:
        lead = transition_lead_stage(
            db, lead_id, payload.to_stage,
            changed_by=payload.changed_by,
            reason=payload.reason,
        )
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/leads/{lead_id}/stage-history", response_model=list[StageHistoryResponse])
def get_lead_stage_history(lead_id: int, db: Session = Depends(get_db)):
    return (
        db.query(LeadStageHistory)
        .filter(LeadStageHistory.lead_id == lead_id)
        .order_by(LeadStageHistory.created_at.desc())
        .all()
    )


@router.get("/leads/{lead_id}/do-not-contact")
def get_do_not_contact(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {
        "lead_id": lead.id,
        "do_not_contact": lead.do_not_contact,
        "reason": lead.do_not_contact_reason,
    }


@router.post("/leads/{lead_id}/do-not-contact")
def set_do_not_contact(
    lead_id: int,
    reason: str = "Opted out",
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.do_not_contact:
        lead.do_not_contact = True
        lead.do_not_contact_reason = reason
        history = LeadStageHistory(
            lead_id=lead_id,
            from_stage=lead.stage,
            to_stage=LeadStage.do_not_contact.value,
            changed_by="system",
            reason=reason,
        )
        db.add(history)
        lead.stage = LeadStage.do_not_contact.value
        log_audit_event(
            db, "opt_out", "lead", str(lead_id),
            actor="system", details={"reason": reason},
        )
        db.commit()
    db.refresh(lead)
    return {"lead_id": lead.id, "do_not_contact": True}


# --- Follow-ups ---

@router.get("/follow-ups/due")
def list_follow_ups_due():
    candidates = get_follow_up_candidates()
    result = []
    for msg in candidates:
        result.append(FollowUpCandidateResponse(
            message_id=msg.id,
            lead_id=msg.lead_id,
            lead_name="",
            channel=msg.channel,
            follow_up_number=msg.follow_up_number,
            last_sent_at=msg.sent_at,
        ))
    return result


@router.post("/follow-ups/{message_id}/generate")
def generate_follow_up(
    message_id: str,
    db: Session = Depends(get_db),
):
    original = db.query(OutreachMessage).filter(
        OutreachMessage.id == message_id
    ).first()
    if not original:
        raise HTTPException(status_code=404, detail="Message not found")

    lead = db.query(Lead).filter(Lead.id == original.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if original.follow_up_number >= settings.follow_up_max_count:
        raise HTTPException(status_code=400, detail="Max follow-ups reached")

    landing = None
    if lead.landings:
        for lp in lead.landings:
            if lp.preview_url:
                landing = lp
                break
        if not landing:
            landing = lead.landings[0]

    ctx = MessageContext(
        company_name=lead.name,
        city=lead.city or "",
        category=lead.category or "",
        preview_url=landing.preview_url if landing else "",
        phone=lead.phone or "",
        language="ru",
        follow_up_number=original.follow_up_number + 1,
    )
    generated = generate_messages(ctx)

    new_msg = OutreachMessage(
        id=str(uuid.uuid4())[:12],
        campaign_id=original.campaign_id,
        lead_id=original.lead_id,
        channel=original.channel,
        recipient=original.recipient,
        body=generated.follow_up,
        subject=original.subject,
        status=MessageStatus.needs_review.value,
        follow_up_number=original.follow_up_number + 1,
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg


# --- Webhooks ---
# WhatsApp webhooks are handled by whatsapp_routes.py
# (signed verification + inbound message handling + template management)


@router.post("/webhooks/email")
async def webhook_email(request: Request):
    payload = await request.json()
    from app.outreach.webhook_handler import process_webhook_event
    result = process_webhook_event("email", payload)
    return result


@router.post("/webhooks/telegram")
async def webhook_telegram(request: Request):
    payload = await request.json()
    from app.outreach.webhook_handler import process_webhook_event
    result = process_webhook_event("telegram", payload)
    return result


# --- Metrics ---

@router.get("/metrics/outreach")
def get_outreach_metrics_endpoint():
    return get_outreach_metrics()


# --- Audit Log ---

@router.get("/audit-log", response_model=list[AuditLogResponse])
def list_audit_log(
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()
