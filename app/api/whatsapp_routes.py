from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.campaign import MessageStatus, OutreachMessage
from app.models.event import OutreachEvent
from app.models.lead import ConsentStatus, Lead
from app.models.whatsapp import InboundMessage, InboundMessageStatus, WhatsAppTemplate, WhatsAppTemplateStatus
from app.outreach.phone import PhoneNumberError, PhoneNumberService
from app.security.webhook_signature import verify_whatsapp_signature

router = APIRouter()


class TemplatePayload(BaseModel):
    name: str
    language_code: str = "ru"
    category: str | None = None
    body_template: str
    status: str = WhatsAppTemplateStatus.draft.value


class ConsentPayload(BaseModel):
    consent_status: str
    contact_basis: str | None = None
    consent_source: str | None = None
    consent_notes: str | None = None


@router.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token, settings.whatsapp_webhook_verify_token):
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhooks/whatsapp")
async def receive_whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not verify_whatsapp_signature(raw, request.headers.get("X-Hub-Signature-256")):
        return {"status": "ok", "changed": 0, "processed": False, "reason": "invalid_signature"}
    payload = json.loads(raw or b"{}")
    changed = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            for status in value.get("statuses", []):
                provider_id = status.get("id")
                state = status.get("status")
                msg = db.query(OutreachMessage).filter(OutreachMessage.provider_message_id == provider_id).first()
                if not msg or state not in {"sent", "delivered", "read", "failed"}:
                    continue
                event_key = f"wa:{provider_id}:{state}:{status.get('timestamp', '')}"
                if db.query(OutreachEvent).filter(OutreachEvent.provider_event_id == event_key).first():
                    continue
                msg.status = state
                now = datetime.now(timezone.utc)
                if state == "delivered": msg.delivered_at = now
                if state == "read": msg.read_at = now
                if state == "failed": msg.failed_at = now
                db.add(OutreachEvent(id=str(uuid.uuid4())[:50], message_id=msg.id, event_type=state, provider_event_id=event_key, payload_json=json.dumps({"status": state})))
                changed += 1
            for item in value.get("messages", []):
                provider_id = item.get("id")
                if not provider_id or db.query(InboundMessage).filter(InboundMessage.provider_message_id == provider_id).first():
                    continue
                try:
                    phone = PhoneNumberService.normalize(item.get("from"))
                except PhoneNumberError:
                    continue
                lead = db.query(Lead).filter((Lead.whatsapp == phone) | (Lead.phone == phone)).first()
                message_type = item.get("type", "unknown")
                text = (item.get("text") or {}).get("body")
                inbound = InboundMessage(id=str(uuid.uuid4())[:12], provider_message_id=provider_id, lead_id=lead.id if lead else None, from_phone=phone, message_type=message_type, text_body=text, raw_metadata_json=json.dumps({"type": message_type}))
                db.add(inbound)
                if lead:
                    now = datetime.now(timezone.utc)
                    lead.last_inbound_at = now
                    lead.service_window_expires_at = now + timedelta(hours=settings.whatsapp_service_window_hours)
                    lead.stage = "replied"
                    pending = db.query(OutreachMessage).filter(OutreachMessage.lead_id == lead.id, OutreachMessage.status.in_(["approved", "queued", "retrying"])).all()
                    for message in pending:
                        message.status = MessageStatus.cancelled.value
                        message.error_message = "Cancelled after inbound reply"
                changed += 1
    db.commit()
    return {"status": "ok", "changed": changed}


@router.get("/whatsapp/templates")
def list_templates(status: str | None = None, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(WhatsAppTemplate)
    if status: query = query.filter(WhatsAppTemplate.status == status)
    return query.order_by(WhatsAppTemplate.created_at.desc()).offset(offset).limit(min(limit, 500)).all()


@router.post("/whatsapp/templates")
def create_template(payload: TemplatePayload, db: Session = Depends(get_db)):
    if payload.status not in {item.value for item in WhatsAppTemplateStatus}:
        raise HTTPException(status_code=400, detail="Invalid template status")
    template = WhatsAppTemplate(id=str(uuid.uuid4())[:12], **payload.model_dump())
    db.add(template); db.commit(); db.refresh(template)
    return template


@router.get("/inbound-messages")
def list_inbound_messages(lead_id: int | None = None, status: str | None = None, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(InboundMessage)
    if lead_id: query = query.filter(InboundMessage.lead_id == lead_id)
    if status: query = query.filter(InboundMessage.status == status)
    return query.order_by(InboundMessage.received_at.desc()).offset(offset).limit(min(limit, 500)).all()


@router.post("/inbound-messages/{message_id}/mark-handled")
def mark_inbound_handled(message_id: str, db: Session = Depends(get_db)):
    message = db.query(InboundMessage).filter(InboundMessage.id == message_id).first()
    if not message: raise HTTPException(status_code=404, detail="Inbound message not found")
    message.status = InboundMessageStatus.handled.value
    message.processed_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(message)
    return message


@router.put("/leads/{lead_id}/consent")
def update_consent(lead_id: int, payload: ConsentPayload, db: Session = Depends(get_db)):
    if payload.consent_status not in {item.value for item in ConsentStatus}:
        raise HTTPException(status_code=400, detail="Invalid consent status")
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead: raise HTTPException(status_code=404, detail="Lead not found")
    lead.consent_status = payload.consent_status
    lead.contact_basis = payload.contact_basis
    lead.consent_source = payload.consent_source
    lead.consent_notes = payload.consent_notes
    lead.consent_recorded_at = datetime.now(timezone.utc)
    if payload.consent_status in {ConsentStatus.withdrawn.value, ConsentStatus.blocked.value}:
        lead.do_not_contact = True
    db.commit(); db.refresh(lead)
    return lead
