import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.campaign import OutreachMessage, MessageStatus
from app.models.event import OutreachEvent
from app.models.lead import Lead
from app.models.stage import LeadStage

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "delivered": MessageStatus.delivered.value,
    "read": MessageStatus.read.value,
    "failed": MessageStatus.failed.value,
    "replied": MessageStatus.replied.value,
}


def process_webhook_event(
    provider: str,
    payload: dict,
    provider_event_id: str | None = None,
    signature_valid: bool = True,
) -> dict:
    if not signature_valid:
        logger.warning("Invalid webhook signature for %s", provider)
        return {"processed": False, "reason": "invalid_signature"}

    provider_message_id = _extract_provider_message_id(provider, payload)
    if not provider_message_id:
        return {"processed": False, "reason": "no_message_id"}

    event_type = _extract_event_type(provider, payload)

    db: Session = SessionLocal()
    try:
        msg = (
            db.query(OutreachMessage)
            .filter(OutreachMessage.provider_message_id == provider_message_id)
            .first()
        )
        if not msg:
            return {"processed": False, "reason": "message_not_found"}

        existing = (
            db.query(OutreachEvent)
            .filter(
                OutreachEvent.message_id == msg.id,
                OutreachEvent.event_type == event_type,
            )
            .first()
        )
        if existing:
            return {"processed": False, "reason": "duplicate_event"}

        safe_payload = json.dumps(
            _redact_secrets(payload), ensure_ascii=False, default=str
        )[:5000]

        event = OutreachEvent(
            id=str(uuid.uuid4())[:20],
            message_id=msg.id,
            event_type=event_type,
            provider_event_id=provider_event_id,
            payload_json=safe_payload,
        )
        db.add(event)

        new_status = _STATUS_MAP.get(event_type)
        if new_status and _is_monotonic(msg.status, new_status):
            msg.status = new_status
            now = datetime.now(timezone.utc)
            if new_status == MessageStatus.delivered.value:
                msg.delivered_at = now
            elif new_status == MessageStatus.read.value:
                msg.read_at = now
            elif new_status == MessageStatus.failed.value:
                msg.failed_at = now
                msg.error_message = _extract_error(provider, payload)
            elif new_status == MessageStatus.replied.value:
                msg.replied_at = now
                _update_lead_stage_replied(db, msg.lead_id)

        db.commit()
        return {"processed": True, "event_type": event_type}
    except Exception as e:
        logger.exception("Webhook processing failed")
        db.rollback()
        return {"processed": False, "reason": str(e)}
    finally:
        db.close()


def _extract_provider_message_id(provider: str, payload: dict) -> str | None:
    if provider == "whatsapp":
        entry = payload.get("entry", [{}])
        if entry:
            changes = entry[0].get("changes", [{}])
            if changes:
                value = changes[0].get("value", {})
                messages = value.get("messages", [])
                if messages:
                    return messages[0].get("id")
                statuses = value.get("statuses", [])
                if statuses:
                    return statuses[0].get("id")
    elif provider == "email":
        return payload.get("Message-Id") or payload.get("message_id")
    elif provider == "telegram":
        msg = payload.get("message", {})
        return str(msg.get("message_id")) if msg else None
    return None


def _extract_event_type(provider: str, payload: dict) -> str:
    if provider == "whatsapp":
        entry = payload.get("entry", [{}])
        if entry:
            changes = entry[0].get("changes", [{}])
            if changes:
                value = changes[0].get("value", {})
                if "messages" in value:
                    return "replied"
                statuses = value.get("statuses", [])
                if statuses:
                    status_field = statuses[0].get("status", "")
                    return status_field
    elif provider == "telegram":
        msg = payload.get("message", {})
        if msg:
            return "replied"
    return "unknown"


def _extract_error(provider: str, payload: dict) -> str | None:
    if provider == "whatsapp":
        entry = payload.get("entry", [{}])
        if entry:
            changes = entry[0].get("changes", [{}])
            if changes:
                statuses = changes[0].get("value", {}).get("statuses", [])
                if statuses:
                    errors = statuses[0].get("errors", [])
                    if errors:
                        return errors[0].get("message", "Provider error")
    return None


def _is_monotonic(current: str, new: str) -> bool:
    order = [
        MessageStatus.draft.value,
        MessageStatus.needs_review.value,
        MessageStatus.approved.value,
        MessageStatus.queued.value,
        MessageStatus.sent.value,
        MessageStatus.delivered.value,
        MessageStatus.read.value,
        MessageStatus.replied.value,
    ]
    try:
        return order.index(new) >= order.index(current)
    except ValueError:
        return True


def _redact_secrets(payload: dict) -> dict:
    result = {}
    for k, v in payload.items():
        if k.lower() in ("token", "secret", "password", "api_key", "authorization"):
            result[k] = "***REDACTED***"
        elif isinstance(v, dict):
            result[k] = _redact_secrets(v)
        else:
            result[k] = v
    return result


def _update_lead_stage_replied(db: Session, lead_id: int) -> None:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if lead and lead.stage not in (
        LeadStage.won.value,
        LeadStage.lost.value,
        LeadStage.do_not_contact.value,
    ):
        lead.stage = LeadStage.replied.value
