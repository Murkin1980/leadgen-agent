from __future__ import annotations

import logging
from datetime import datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.config import settings
from app.database import SessionLocal
from app.models.campaign import OutreachMessage, MessageStatus, OutreachCampaign, CampaignStatus
from app.models.lead import Lead

logger = logging.getLogger(__name__)


def is_quiet_hours() -> bool:
    tz = ZoneInfo(settings.outreach_timezone)
    now = datetime.now(tz).time()
    start = time.fromisoformat(settings.outreach_quiet_hours_start)
    end = time.fromisoformat(settings.outreach_quiet_hours_end)
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def check_hourly_rate_limit() -> bool:
    db = SessionLocal()
    try:
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        count = (
            db.query(func.count(OutreachMessage.id))
            .filter(
                OutreachMessage.status.in_([
                    MessageStatus.sent.value,
                    MessageStatus.queued.value,
                ]),
                OutreachMessage.sent_at >= one_hour_ago,
            )
            .scalar()
        )
        return (count or 0) < settings.outreach_max_per_hour
    finally:
        db.close()


def is_duplicate_first_contact(lead_id: int, channel: str, campaign_id: str) -> bool:
    db = SessionLocal()
    try:
        existing = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.lead_id == lead_id,
                OutreachMessage.channel == channel,
                OutreachMessage.campaign_id == campaign_id,
            )
            .first()
        )
        return existing is not None
    finally:
        db.close()


def can_send_message(message: OutreachMessage) -> tuple[bool, str]:
    if not settings.outreach_enabled:
        return False, "Outreach is disabled (OUTREACH_ENABLED=false)"

    if message.status != MessageStatus.approved.value:
        return False, f"Message status is '{message.status}', must be 'approved'"

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == message.lead_id).first()
        if lead and lead.do_not_contact:
            return False, f"Lead is do_not_contact: {lead.do_not_contact_reason or 'no reason'}"

        campaign = db.query(OutreachCampaign).filter(
            OutreachCampaign.id == message.campaign_id
        ).first()
        if campaign and campaign.status in (
            CampaignStatus.paused.value,
            CampaignStatus.cancelled.value,
        ):
            return False, f"Campaign is {campaign.status}"

        if is_quiet_hours():
            return False, "Quiet hours active"

        if not check_hourly_rate_limit():
            return False, "Hourly rate limit exceeded"
    finally:
        db.close()

    return True, "ok"


def get_follow_up_candidates() -> list[OutreachMessage]:
    if not settings.follow_up_enabled:
        return []

    db = SessionLocal()
    try:
        delay_threshold = datetime.now(timezone.utc) - timedelta(
            hours=settings.follow_up_delay_hours
        )

        candidates = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.status.in_([
                    MessageStatus.sent.value,
                    MessageStatus.delivered.value,
                ]),
                OutreachMessage.follow_up_number < settings.follow_up_max_count,
                OutreachMessage.sent_at <= delay_threshold,
                OutreachMessage.replied_at.is_(None),
            )
            .all()
        )

        result = []
        for msg in candidates:
            lead = db.query(Lead).filter(Lead.id == msg.lead_id).first()
            if not lead:
                continue
            if lead.do_not_contact:
                continue
            if lead.stage in ("replied", "won", "lost", "do_not_contact"):
                continue
            result.append(msg)

        return result
    finally:
        db.close()


def get_outreach_metrics() -> dict:
    db = SessionLocal()
    try:
        status_counts = {}
        for status in MessageStatus:
            count = (
                db.query(func.count(OutreachMessage.id))
                .filter(OutreachMessage.status == status.value)
                .scalar()
            )
            status_counts[status.value] = count or 0

        total_sent = status_counts.get("sent", 0) + status_counts.get("delivered", 0) + status_counts.get("read", 0)
        replied = status_counts.get("replied", 0)
        reply_rate = (replied / total_sent * 100) if total_sent > 0 else 0.0

        stage_counts = {}
        from app.models.lead import Lead
        leads = db.query(Lead).all()
        for lead in leads:
            stage_counts[lead.stage] = stage_counts.get(lead.stage, 0) + 1

        return {
            "draft_count": status_counts.get("draft", 0) + status_counts.get("needs_review", 0),
            "approved_count": status_counts.get("approved", 0),
            "sent_count": total_sent,
            "delivered_count": status_counts.get("delivered", 0),
            "replied_count": replied,
            "failed_count": status_counts.get("failed", 0),
            "opt_out_count": status_counts.get("blocked", 0),
            "reply_rate": round(reply_rate, 2),
            "conversion_by_stage": stage_counts,
        }
    finally:
        db.close()
