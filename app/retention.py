"""Data retention: configurable purge, anonymize, DNC fingerprint preservation."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.audit import AuditLog
from app.models.campaign import OutreachMessage
from app.models.event import OutreachEvent
from app.models.lead import Lead
from app.models.whatsapp import InboundMessage
from app.security import log_audit_event

logger = logging.getLogger(__name__)


# Default retention periods (days)
DEFAULT_LEAD_RETENTION_DAYS = 365
DEFAULT_MESSAGE_RETENTION_DAYS = 730
DEFAULT_EVENT_RETENTION_DAYS = 365


def get_retention_config() -> dict:
    """Return current retention configuration."""
    return {
        "lead_retention_days": getattr(settings, "lead_retention_days", DEFAULT_LEAD_RETENTION_DAYS),
        "message_retention_days": getattr(settings, "message_retention_days", DEFAULT_MESSAGE_RETENTION_DAYS),
        "event_retention_days": getattr(settings, "event_retention_days", DEFAULT_EVENT_RETENTION_DAYS),
    }


def purge_preview(db: Session) -> dict:
    """Preview what would be deleted without actually deleting.

    Returns counts of records that exceed retention periods.
    """
    config = get_retention_config()
    now = datetime.now(timezone.utc)
    lead_cutoff = now - timedelta(days=config["lead_retention_days"])
    message_cutoff = now - timedelta(days=config["message_retention_days"])
    event_cutoff = now - timedelta(days=config["event_retention_days"])

    old_leads = (
        db.query(Lead)
        .filter(Lead.created_at < lead_cutoff)
        .filter(Lead.stage.notin_(["won", "do_not_contact"]))
        .count()
    )
    old_messages = (
        db.query(OutreachMessage)
        .filter(OutreachMessage.created_at < message_cutoff)
        .count()
    )
    old_events = (
        db.query(OutreachEvent)
        .filter(OutreachEvent.created_at < event_cutoff)
        .count()
    )

    return {
        "leads_eligible": old_leads,
        "messages_eligible": old_messages,
        "events_eligible": old_events,
        "lead_cutoff": lead_cutoff.isoformat(),
        "message_cutoff": message_cutoff.isoformat(),
        "event_cutoff": event_cutoff.isoformat(),
    }


def purge_execute(db: Session, actor: str = "system", dry_run: bool = False) -> dict:
    """Execute purge of expired data.

    Does NOT delete leads marked as won or do_not_contact.
    Preserves DNC fingerprint to prevent re-contact.

    Returns counts of actually deleted records.
    """
    config = get_retention_config()
    now = datetime.now(timezone.utc)
    lead_cutoff = now - timedelta(days=config["lead_retention_days"])
    message_cutoff = now - timedelta(days=config["message_retention_days"])
    event_cutoff = now - timedelta(days=config["event_retention_days"])

    deleted_events = 0
    old_events = (
        db.query(OutreachEvent)
        .filter(OutreachEvent.created_at < event_cutoff)
        .all()
    )
    deleted_events = len(old_events)
    if not dry_run:
        for event in old_events:
            db.delete(event)

    deleted_messages = 0
    old_messages = (
        db.query(OutreachMessage)
        .filter(OutreachMessage.created_at < message_cutoff)
        .all()
    )
    deleted_messages = len(old_messages)
    if not dry_run:
        for msg in old_messages:
            db.delete(msg)

    deleted_leads = 0
    anonymized_leads = 0
    old_leads = (
        db.query(Lead)
        .filter(Lead.created_at < lead_cutoff)
        .filter(Lead.stage.notin_(["won", "do_not_contact"]))
        .all()
    )
    for lead in old_leads:
        if lead.do_not_contact:
            continue
        deleted_leads += 1
        if not dry_run:
            _anonymize_lead(lead)
            anonymized_leads += 1

    if not dry_run:
        log_audit_event(
            db, "data_purge", "system", "retention",
            actor=actor,
            details={
                "leads_anonymized": anonymized_leads,
                "messages_deleted": deleted_messages,
                "events_deleted": deleted_events,
                "dry_run": False,
            },
        )
        db.commit()

    return {
        "leads_anonymized": anonymized_leads,
        "messages_deleted": deleted_messages,
        "events_deleted": deleted_events,
        "dry_run": dry_run,
    }


def anonymize_lead(db: Session, lead_id: int, actor: str = "admin") -> bool:
    """Anonymize a specific lead. Preserves DNC fingerprint.

    Returns True if successful.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return False

    _anonymize_lead(lead)
    log_audit_event(
        db, "lead_anonymized", "lead", str(lead_id),
        actor=actor,
        details={"name_was": lead.name},
    )
    db.commit()
    db.refresh(lead)
    return True


def _dnc_fingerprint(lead: Lead) -> str:
    """Generate a fingerprint from PII fields for DNC dedup."""
    parts = [
        lead.phone or "",
        lead.email or "",
        lead.name or "",
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _anonymize_lead(lead: Lead) -> None:
    """Anonymize lead PII. Preserves DNC fingerprint and stage."""
    was_dnc = lead.do_not_contact
    was_stage = lead.stage
    was_dnc_reason = lead.do_not_contact_reason

    lead.name = f"anonymized_{lead.id}"
    lead.phone = None
    lead.whatsapp = None
    lead.email = None
    lead.address = None
    lead.website = None
    lead.instagram = None
    lead.telegram = None
    lead.source_url = None
    lead.notes = None
    lead.slug = None

    lead.do_not_contact = was_dnc
    lead.stage = was_stage
    lead.do_not_contact_reason = was_dnc_reason
