"""Pilot safeguards: PILOT_MODE controls, limits, kill switch."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.campaign import OutreachMessage
from app.models.lead import Lead
from app.security import log_audit_event

logger = logging.getLogger(__name__)

# Pilot mode constants
PILOT_MAX_LEADS = 5
PILOT_MAX_MESSAGES_PER_LEAD = 2
PILOT_MAX_TOTAL_MESSAGES = 10


def is_pilot_mode() -> bool:
    """Check if pilot mode is active."""
    return getattr(settings, "pilot_mode", False)


def pilot_allows_operation(db: Session) -> tuple[bool, str]:
    """Check if an operation is allowed under pilot mode.

    Returns (allowed, reason).
    """
    if not is_pilot_mode():
        return True, "not in pilot mode"

    lead_count = db.query(Lead).filter(Lead.status.notin_(["deleted"])).count()
    if lead_count >= PILOT_MAX_LEADS:
        return False, f"Pilot limit: max {PILOT_MAX_LEADS} leads reached"

    return True, "pilot mode active"


def pilot_validate_lead_count(db: Session) -> tuple[bool, str]:
    """Validate lead count against pilot limit."""
    if not is_pilot_mode():
        return True, "not in pilot mode"

    count = db.query(Lead).filter(Lead.status.notin_(["deleted"])).count()
    if count >= PILOT_MAX_LEADS:
        return False, f"Cannot add more leads: pilot limit of {PILOT_MAX_LEADS} reached (currently {count})"
    return True, f"{count}/{PILOT_MAX_LEADS} leads"


def pilot_validate_message(
    db: Session,
    lead_id: int,
) -> tuple[bool, str]:
    """Validate message send against pilot limits.

    Returns (allowed, reason).
    """
    if not is_pilot_mode():
        return True, "not in pilot mode"

    total_messages = db.query(OutreachMessage).count()
    if total_messages >= PILOT_MAX_TOTAL_MESSAGES:
        return False, f"Pilot total message limit of {PILOT_MAX_TOTAL_MESSAGES} reached"

    lead_messages = (
        db.query(OutreachMessage)
        .filter(OutreachMessage.lead_id == lead_id)
        .count()
    )
    if lead_messages >= PILOT_MAX_MESSAGES_PER_LEAD:
        return False, f"Per-lead message limit of {PILOT_MAX_MESSAGES_PER_LEAD} reached"

    return True, "allowed"


def pilot_kill_switch(db: Session, actor: str = "admin") -> dict[str, Any]:
    """Emergency kill switch: cancel all pending messages and pause outreach.

    Returns action summary.
    """
    from app.models.campaign import MessageStatus

    cancelled = (
        db.query(OutreachMessage)
        .filter(
            OutreachMessage.status.in_([
                MessageStatus.needs_review.value,
                MessageStatus.approved.value,
                MessageStatus.queued.value,
                MessageStatus.sending.value,
            ])
        )
        .update({"status": MessageStatus.cancelled.value})
    )
    log_audit_event(
        db, "pilot_kill_switch", "pilot", "all",
        actor=actor,
        details={"cancelled_messages": cancelled},
    )
    db.commit()

    return {
        "cancelled_messages": cancelled,
        "pilot_mode": True,
        "message": "All pending messages cancelled. Pilot mode is still active.",
    }


def pilot_status(db: Session) -> dict[str, Any]:
    """Get current pilot mode status."""
    is_active = is_pilot_mode()
    lead_count = db.query(Lead).filter(Lead.status.notin_(["deleted"])).count() if is_active else 0
    message_count = db.query(OutreachMessage).count() if is_active else 0
    pending = (
        db.query(OutreachMessage)
        .filter(OutreachMessage.status.in_(["needs_review", "approved", "queued", "sending"]))
        .count()
        if is_active
        else 0
    )

    return {
        "pilot_mode": is_active,
        "leads": {
            "count": lead_count,
            "limit": PILOT_MAX_LEADS if is_active else None,
        },
        "messages": {
            "total": message_count,
            "pending": pending,
            "limit": PILOT_MAX_TOTAL_MESSAGES if is_active else None,
            "per_lead_limit": PILOT_MAX_MESSAGES_PER_LEAD if is_active else None,
        },
        "kill_switch_available": is_active,
    }


def pilot_report(db: Session) -> dict[str, Any]:
    """Generate pilot report: leads, messages, outcomes."""
    from app.models.campaign import MessageStatus

    if not is_pilot_mode():
        return {"pilot_mode": False, "message": "Not in pilot mode"}

    leads = db.query(Lead).filter(Lead.status.notin_(["deleted"])).all()
    messages = db.query(OutreachMessage).all()

    delivered = sum(1 for m in messages if m.status == MessageStatus.delivered.value)
    failed = sum(1 for m in messages if m.status == MessageStatus.failed.value)
    dead_letter = sum(1 for m in messages if m.status == MessageStatus.dead_letter.value)

    return {
        "pilot_mode": True,
        "leads_total": len(leads),
        "messages_total": len(messages),
        "delivered": delivered,
        "failed": failed,
        "dead_letter": dead_letter,
        "delivery_rate": f"{(delivered / len(messages) * 100):.1f}%" if messages else "N/A",
    }
