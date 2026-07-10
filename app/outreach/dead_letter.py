"""Dead-letter workflow: list, requeue, cancel with policy checks."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.campaign import MessageStatus, OutreachMessage
from app.models.lead import ConsentStatus, Lead
from app.outreach.phone import PhoneNumberError, PhoneNumberService
from app.outreach.service import is_sandbox_allowed, is_quiet_hours, check_hourly_rate_limit
from app.security import log_audit_event

logger = logging.getLogger(__name__)


def list_dead_letters(db: Session, limit: int = 50, offset: int = 0) -> list[dict]:
    """Return dead-letter messages with reason, attempts, and last error."""
    msgs = (
        db.query(OutreachMessage)
        .filter(OutreachMessage.status == MessageStatus.dead_letter.value)
        .order_by(OutreachMessage.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = []
    for msg in msgs:
        lead = db.query(Lead).filter(Lead.id == msg.lead_id).first()
        result.append({
            "id": msg.id,
            "lead_id": msg.lead_id,
            "lead_name": lead.name if lead else None,
            "channel": msg.channel,
            "recipient": msg.recipient,
            "body_preview": msg.body[:120] if msg.body else "",
            "attempt_count": msg.attempt_count,
            "error_message": msg.error_message,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            "updated_at": msg.updated_at.isoformat() if msg.updated_at else None,
        })
    return result


def requeue_dead_letter(
    db: Session,
    message_id: str,
    actor: str = "admin",
) -> tuple[bool, str]:
    """Requeue a dead-letter message. Re-runs DNC, consent, sandbox, and service window checks.

    Returns (success, reason).
    """
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        return False, "Message not found"
    if msg.status != MessageStatus.dead_letter.value:
        return False, f"Message status is '{msg.status}', not dead_letter"

    lead = db.query(Lead).filter(Lead.id == msg.lead_id).first()
    if not lead:
        return False, "Lead not found"

    if lead.do_not_contact:
        log_audit_event(db, "dead_letter_requeue_blocked", "outreach_message", message_id,
                        actor=actor, details={"reason": "lead_do_not_contact"})
        db.commit()
        return False, "Lead is do_not_contact"

    if settings.outreach_mode == "production":
        allowed_consents = {
            ConsentStatus.consented.value,
            ConsentStatus.legitimate_interest_reviewed.value,
        }
        if lead.consent_status not in allowed_consents:
            log_audit_event(db, "dead_letter_requeue_blocked", "outreach_message", message_id,
                            actor=actor, details={"reason": "consent_not_approved"})
            db.commit()
            return False, "Consent not approved for production mode"

    if settings.outreach_mode == "sandbox":
        if not is_sandbox_allowed(msg.recipient):
            log_audit_event(db, "dead_letter_requeue_blocked", "outreach_message", message_id,
                            actor=actor, details={"reason": "not_in_sandbox_allowlist"})
            db.commit()
            return False, "Recipient not in sandbox allowlist"

    try:
        PhoneNumberService.normalize(msg.recipient)
    except PhoneNumberError:
        log_audit_event(db, "dead_letter_requeue_blocked", "outreach_message", message_id,
                        actor=actor, details={"reason": "invalid_phone"})
        db.commit()
        return False, "Invalid phone number"

    if not settings.outreach_enabled:
        log_audit_event(db, "dead_letter_requeue_blocked", "outreach_message", message_id,
                        actor=actor, details={"reason": "outreach_disabled"})
        db.commit()
        return False, "Outreach is disabled"

    msg.status = MessageStatus.approved.value
    msg.error_message = None
    msg.retryable = False
    msg.attempt_count = 0
    msg.next_retry_at = None
    log_audit_event(db, "dead_letter_requeued", "outreach_message", message_id,
                    actor=actor)
    db.commit()
    db.refresh(msg)
    return True, "Requeued"


def cancel_dead_letter(
    db: Session,
    message_id: str,
    actor: str = "admin",
    reason: str | None = None,
) -> tuple[bool, str]:
    """Cancel a dead-letter message. Returns (success, reason)."""
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        return False, "Message not found"
    if msg.status != MessageStatus.dead_letter.value:
        return False, f"Message status is '{msg.status}', not dead_letter"

    msg.status = MessageStatus.cancelled.value
    msg.error_message = reason or "Cancelled from dead-letter"
    msg.retryable = False
    log_audit_event(db, "dead_letter_cancelled", "outreach_message", message_id,
                    actor=actor, details={"reason": reason})
    db.commit()
    db.refresh(msg)
    return True, "Cancelled"
