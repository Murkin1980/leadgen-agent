import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

from rq import Queue
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.campaign import MessageStatus, OutreachCampaign, OutreachMessage
from app.models.event import OutreachEvent
from app.models.lead import ConsentStatus, Lead
from app.models.stage import LeadStage
from app.outreach.factory import create_outreach_provider
from app.outreach.phone import PhoneNumberError, PhoneNumberService
from app.outreach.service import can_send_message
from app.security import log_audit_event
from app.workers.connection import redis_conn

logger = logging.getLogger(__name__)


def _service_window_active(lead: Lead, now: datetime) -> bool:
    return bool(lead.service_window_expires_at and lead.service_window_expires_at > now)


def _production_policy_allows(lead: Lead, recipient: str) -> tuple[bool, str | None]:
    if settings.outreach_mode == "disabled" or not settings.outreach_enabled:
        return False, "Outreach is disabled"
    try:
        normalized = PhoneNumberService.normalize(recipient)
    except PhoneNumberError as exc:
        return False, str(exc)
    if settings.outreach_mode == "sandbox" and normalized not in settings.sandbox_allowlist:
        return False, "Recipient is not in sandbox allowlist"
    if lead.do_not_contact:
        return False, "Lead is do-not-contact"
    allowed_consents = {
        ConsentStatus.consented.value,
        ConsentStatus.legitimate_interest_reviewed.value,
    }
    if settings.outreach_mode == "production" and lead.consent_status not in allowed_consents:
        return False, "Contact basis is not approved"
    return True, None


def _schedule_retry(msg: OutreachMessage, error: str) -> None:
    msg.attempt_count += 1
    msg.retryable = True
    if msg.attempt_count > settings.outreach_send_max_retries:
        msg.status = MessageStatus.dead_letter.value
        msg.error_message = error[:2000]
        return
    delay = settings.outreach_send_retry_base_seconds * (2 ** max(0, msg.attempt_count - 1))
    delay += random.randint(0, max(1, delay // 5))
    msg.status = MessageStatus.retrying.value
    msg.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    msg.error_message = error[:2000]
    Queue("outreach_send", connection=redis_conn).enqueue_in(
        timedelta(seconds=delay),
        "app.workers.outreach_sender_worker.run_outreach_sender",
        msg.id,
        job_timeout=settings.outreach_send_job_timeout_seconds,
    )


def run_outreach_sender(message_id: str) -> None:
    db: Session = SessionLocal()
    try:
        msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).with_for_update().first()
        if not msg:
            logger.error("Message %s not found", message_id)
            return
        if msg.status in {MessageStatus.sent.value, MessageStatus.delivered.value, MessageStatus.read.value, MessageStatus.replied.value, MessageStatus.cancelled.value}:
            return

        allowed, reason = can_send_message(msg)
        lead = db.query(Lead).filter(Lead.id == msg.lead_id).first()
        if not lead:
            allowed, reason = False, "Lead not found"
        if allowed:
            allowed, reason = _production_policy_allows(lead, msg.recipient)
        if not allowed:
            msg.status = MessageStatus.blocked.value
            msg.retryable = False
            msg.error_message = reason
            log_audit_event(db, "message_blocked", "outreach_message", message_id, actor="system")
            db.commit()
            return

        if not msg.idempotency_key:
            msg.idempotency_key = str(uuid.uuid4())
        msg.attempt_count += 1
        db.commit()

        provider = create_outreach_provider()
        now = datetime.now(timezone.utc)
        result = provider.send(
            recipient=msg.recipient,
            body=msg.body,
            subject=msg.subject,
            template_name=msg.template_name if msg.is_template else None,
            language_code=msg.template_language or "ru",
            service_window_active=_service_window_active(lead, now),
            idempotency_key=msg.idempotency_key,
        )

        if result.success:
            msg.status = MessageStatus.sent.value
            msg.sent_at = now
            msg.provider_message_id = result.provider_message_id
            msg.retryable = False
            msg.next_retry_at = None
            db.add(OutreachEvent(
                id=str(uuid.uuid4())[:50],
                message_id=message_id,
                event_type="sent",
                provider_event_id=result.provider_message_id,
                payload_json=str(result.raw_response),
            ))
            lead.last_contacted_at = now
            lead.last_outbound_at = now
            if lead.stage == LeadStage.ready_for_outreach.value:
                lead.stage = LeadStage.contacted.value
            log_audit_event(db, "message_sent", "outreach_message", message_id, actor="system")
        elif result.retryable:
            # attempt_count was already incremented before the API call
            msg.attempt_count -= 1
            _schedule_retry(msg, result.error_message or "Temporary send failure")
            log_audit_event(db, "message_retry_scheduled", "outreach_message", message_id, actor="system")
        else:
            msg.status = MessageStatus.failed.value
            msg.failed_at = now
            msg.retryable = False
            msg.error_message = result.error_message or "Send failed"
            log_audit_event(db, "message_failed", "outreach_message", message_id, actor="system")
        db.commit()

    except Exception as exc:
        logger.exception("Outreach sender crashed for message %s", message_id)
        db.rollback()
        msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
        if msg:
            _schedule_retry(msg, type(exc).__name__)
            db.commit()
    finally:
        db.close()


def run_outreach_sender_batch(campaign_id: str) -> int:
    db = SessionLocal()
    try:
        messages = db.query(OutreachMessage).filter(
            OutreachMessage.campaign_id == campaign_id,
            OutreachMessage.status == MessageStatus.approved.value,
        ).all()
        for msg in messages:
            run_outreach_sender(msg.id)
        return len(messages)
    finally:
        db.close()
