import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.campaign import OutreachMessage, MessageStatus
from app.models.event import OutreachEvent
from app.outreach.factory import create_outreach_provider

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "sent": MessageStatus.sent.value,
    "delivered": MessageStatus.delivered.value,
    "read": MessageStatus.read.value,
    "failed": MessageStatus.failed.value,
}


def run_outreach_status_checker() -> int:
    db: Session = SessionLocal()
    try:
        pending = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.status.in_([
                    MessageStatus.sent.value,
                ]),
                OutreachMessage.provider_message_id.isnot(None),
            )
            .all()
        )

        provider = create_outreach_provider()
        updated = 0

        for msg in pending:
            try:
                status = provider.get_status(msg.provider_message_id)
                new_status = _STATUS_MAP.get(status.value)
                if new_status and new_status != msg.status:
                    old_status = msg.status
                    msg.status = new_status
                    if new_status == MessageStatus.delivered.value:
                        msg.delivered_at = datetime.now(timezone.utc)
                    elif new_status == MessageStatus.read.value:
                        msg.read_at = datetime.now(timezone.utc)
                    elif new_status == MessageStatus.failed.value:
                        msg.failed_at = datetime.now(timezone.utc)

                    event = OutreachEvent(
                        id=str(uuid.uuid4())[:50],
                        message_id=msg.id,
                        event_type=f"status_{new_status}",
                        provider_event_id=msg.provider_message_id,
                        payload_json=f'{{"from": "{old_status}", "to": "{new_status}"}}',
                    )
                    db.add(event)
                    db.commit()
                    updated += 1
            except Exception as e:
                logger.warning("Status check failed for message %s: %s", msg.id, e)

        return updated
    finally:
        db.close()
