import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.campaign import OutreachMessage, MessageStatus, OutreachCampaign, CampaignStatus
from app.models.event import OutreachEvent
from app.models.lead import Lead
from app.models.stage import LeadStage
from app.outreach.factory import create_outreach_provider
from app.outreach.service import can_send_message
from app.security import log_audit_event

logger = logging.getLogger(__name__)


def run_outreach_sender(message_id: str) -> None:
    db: Session = SessionLocal()
    try:
        msg = db.query(OutreachMessage).filter(
            OutreachMessage.id == message_id
        ).first()
        if not msg:
            logger.error("Message %s not found", message_id)
            return

        allowed, reason = can_send_message(msg)
        if not allowed:
            msg.status = MessageStatus.blocked.value
            msg.error_message = reason
            db.commit()
            logger.info("Message %s blocked: %s", message_id, reason)
            return

        provider = create_outreach_provider()

        try:
            result = provider.send(
                recipient=msg.recipient,
                body=msg.body,
                subject=msg.subject,
            )
        except Exception as e:
            msg.status = MessageStatus.failed.value
            msg.failed_at = datetime.now(timezone.utc)
            msg.error_message = str(e)[:2000]
            db.commit()
            logger.error("Message %s send failed: %s", message_id, e)
            return

        if result.success:
            msg.status = MessageStatus.sent.value
            msg.sent_at = datetime.now(timezone.utc)
            msg.provider_message_id = result.provider_message_id

            event = OutreachEvent(
                id=str(hash(f"{message_id}_sent"))[:50],
                message_id=message_id,
                event_type="sent",
                provider_event_id=result.provider_event_id if hasattr(result, "provider_event_id") else result.provider_message_id,
                payload_json=result.raw_response and str(result.raw_response),
            )
            db.add(event)

            lead = db.query(Lead).filter(Lead.id == msg.lead_id).first()
            if lead:
                lead.last_contacted_at = datetime.now(timezone.utc)
                if lead.stage == LeadStage.ready_for_outreach.value:
                    lead.stage = LeadStage.contacted.value

            log_audit_event(
                db, "message_sent", "outreach_message", message_id,
                actor="system",
            )
            db.commit()
        else:
            msg.status = MessageStatus.failed.value
            msg.failed_at = datetime.now(timezone.utc)
            msg.error_message = result.error_message or "Send failed"
            db.commit()

    except Exception as exc:
        logger.exception("Outreach sender crashed for message %s", message_id)
        try:
            msg = db.query(OutreachMessage).filter(
                OutreachMessage.id == message_id
            ).first()
            if msg:
                msg.status = MessageStatus.failed.value
                msg.error_message = str(exc)[:2000]
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def run_outreach_sender_batch(campaign_id: str) -> int:
    db = SessionLocal()
    try:
        messages = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.campaign_id == campaign_id,
                OutreachMessage.status == MessageStatus.approved.value,
            )
            .all()
        )
        sent_count = 0
        for msg in messages:
            run_outreach_sender(msg.id)
            sent_count += 1
        return sent_count
    finally:
        db.close()
