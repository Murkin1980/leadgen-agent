"""Operator inbox: conversation list, unread counts, history, mark handled."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.campaign import OutreachMessage, MessageStatus
from app.models.lead import Lead
from app.models.whatsapp import InboundMessage, InboundMessageStatus

logger = logging.getLogger(__name__)


def list_conversations(
    db: Session,
    lead_id: int | None = None,
    status: str | None = None,
    has_unread: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List conversations with latest inbound/outbound, unread count, service window."""
    leads_q = db.query(Lead)
    if lead_id is not None:
        leads_q = leads_q.filter(Lead.id == lead_id)

    leads = leads_q.order_by(Lead.last_inbound_at.desc()).offset(offset).limit(limit).all()
    now = datetime.now(timezone.utc)
    conversations = []

    for lead in leads:
        last_inbound = (
            db.query(InboundMessage)
            .filter(InboundMessage.lead_id == lead.id)
            .order_by(InboundMessage.received_at.desc())
            .first()
        )
        last_outbound = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.lead_id == lead.id,
                OutreachMessage.status.in_([
                    MessageStatus.sent.value,
                    MessageStatus.delivered.value,
                    MessageStatus.read.value,
                ]),
            )
            .order_by(OutreachMessage.sent_at.desc())
            .first()
        )
        unread_count = (
            db.query(func.count(InboundMessage.id))
            .filter(
                InboundMessage.lead_id == lead.id,
                InboundMessage.status == InboundMessageStatus.new.value,
            )
            .scalar()
            or 0
        )

        service_window_active = bool(
            lead.service_window_expires_at and lead.service_window_expires_at > now
        )
        service_window_expires = (
            lead.service_window_expires_at.isoformat() if lead.service_window_expires_at else None
        )

        conversations.append({
            "lead_id": lead.id,
            "lead_name": lead.name,
            "lead_phone": lead.phone,
            "last_inbound_at": last_inbound.received_at.isoformat() if last_inbound else None,
            "last_inbound_text": last_inbound.text_body[:200] if last_inbound and last_inbound.text_body else None,
            "last_outbound_at": last_outbound.sent_at.isoformat() if last_outbound else None,
            "last_outbound_body": last_outbound.body[:200] if last_outbound else None,
            "unread_count": unread_count,
            "service_window_active": service_window_active,
            "service_window_expires": service_window_expires,
            "consent_status": lead.consent_status,
            "do_not_contact": lead.do_not_contact,
            "stage": lead.stage,
        })

    if has_unread is True:
        conversations = [c for c in conversations if c["unread_count"] > 0]
    elif has_unread is False:
        conversations = [c for c in conversations if c["unread_count"] == 0]

    return conversations


def get_conversation_history(
    db: Session,
    lead_id: int,
    limit: int = 100,
) -> list[dict]:
    """Return full conversation history (inbound + outbound) for a lead, ordered by time."""
    inbounds = (
        db.query(InboundMessage)
        .filter(InboundMessage.lead_id == lead_id)
        .order_by(InboundMessage.received_at.desc())
        .limit(limit)
        .all()
    )
    outbounds = (
        db.query(OutreachMessage)
        .filter(OutreachMessage.lead_id == lead_id)
        .order_by(OutreachMessage.created_at.desc())
        .limit(limit)
        .all()
    )

    messages = []
    for im in inbounds:
        messages.append({
            "direction": "inbound",
            "channel": "whatsapp",
            "text": im.text_body,
            "timestamp": im.received_at.isoformat() if im.received_at else None,
            "status": im.status,
            "message_id": im.id,
        })
    for om in outbounds:
        messages.append({
            "direction": "outbound",
            "channel": om.channel,
            "text": om.body,
            "timestamp": om.sent_at.isoformat() if om.sent_at else (om.created_at.isoformat() if om.created_at else None),
            "status": om.status,
            "message_id": om.id,
        })

    messages.sort(key=lambda m: m["timestamp"] or "", reverse=True)
    return messages[:limit]


def mark_handled(db: Session, message_id: str) -> bool:
    """Mark an inbound message as handled."""
    msg = db.query(InboundMessage).filter(InboundMessage.id == message_id).first()
    if not msg:
        return False
    msg.status = InboundMessageStatus.handled.value
    msg.processed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return True


def can_reply_manually(db: Session, lead_id: int) -> tuple[bool, str]:
    """Check if manual (free-form) reply is allowed inside service window."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return False, "Lead not found"
    if lead.do_not_contact:
        return False, "Lead is do_not_contact"
    now = datetime.now(timezone.utc)
    if lead.service_window_expires_at and lead.service_window_expires_at > now:
        return True, "Service window active"
    return False, "Service window expired — use template reply"


def send_template_reply(
    db: Session,
    lead_id: int,
    body: str,
    template_name: str | None = None,
) -> tuple[bool, str]:
    """Create a template reply message for outside service window.

    Returns (success, reason_or_message_id).
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return False, "Lead not found"
    if lead.do_not_contact:
        return False, "Lead is do_not_contact"

    import uuid
    from datetime import datetime, timezone as tz

    msg = OutreachMessage(
        id=str(uuid.uuid4())[:12],
        campaign_id="",
        lead_id=lead_id,
        channel="whatsapp",
        recipient=lead.phone or lead.whatsapp or "",
        body=body,
        status=MessageStatus.needs_review.value,
        is_template=bool(template_name),
        template_name=template_name,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return True, msg.id
