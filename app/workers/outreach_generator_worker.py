import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.campaign import OutreachCampaign, OutreachMessage, MessageStatus, CampaignStatus
from app.models.lead import Lead
from app.outreach.message_generator import MessageContext, generate_messages

logger = logging.getLogger(__name__)


def run_outreach_generator(campaign_id: str) -> None:
    db: Session = SessionLocal()
    try:
        campaign = db.query(OutreachCampaign).filter(
            OutreachCampaign.id == campaign_id
        ).first()
        if not campaign:
            logger.error("Campaign %s not found", campaign_id)
            return

        campaign.status = CampaignStatus.running.value
        campaign.started_at = datetime.now(timezone.utc)
        db.commit()

        messages = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.campaign_id == campaign_id,
                OutreachMessage.status == MessageStatus.draft.value,
            )
            .all()
        )

        for msg in messages:
            lead = db.query(Lead).filter(Lead.id == msg.lead_id).first()
            if not lead:
                msg.status = MessageStatus.blocked.value
                msg.error_message = "Lead not found"
                db.commit()
                continue

            if lead.do_not_contact:
                msg.status = MessageStatus.blocked.value
                msg.error_message = "Lead marked do_not_contact"
                db.commit()
                continue

            landing = None
            if lead.landings:
                for lp in lead.landings:
                    if lp.preview_url:
                        landing = lp
                        break
                if not landing:
                    landing = lead.landings[0]

            ctx = MessageContext(
                company_name=lead.name,
                city=lead.city or "",
                category=lead.category or "",
                preview_url=landing.preview_url if landing else "",
                phone=lead.phone or "",
                language=campaign.language or "ru",
                follow_up_number=msg.follow_up_number,
            )

            generated = generate_messages(ctx)

            if campaign.channel == "whatsapp":
                msg.body = generated.whatsapp_short
            elif campaign.channel == "email":
                msg.subject = generated.email_subject
                msg.body = generated.email_body
            elif campaign.channel == "telegram":
                msg.body = generated.telegram_body
            elif msg.follow_up_number > 0:
                msg.body = generated.follow_up
            else:
                msg.body = generated.first_contact

            msg.recipient = _get_recipient(lead, campaign.channel)
            msg.status = MessageStatus.needs_review.value
            db.commit()

        campaign.status = CampaignStatus.ready.value
        campaign.completed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as exc:
        logger.exception("Outreach generator failed for campaign %s", campaign_id)
        try:
            campaign = db.query(OutreachCampaign).filter(
                OutreachCampaign.id == campaign_id
            ).first()
            if campaign:
                campaign.status = CampaignStatus.failed.value
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _get_recipient(lead: Lead, channel: str) -> str:
    if channel == "whatsapp":
        return lead.whatsapp or lead.phone or ""
    elif channel == "email":
        return lead.email or ""
    elif channel == "telegram":
        return lead.telegram or ""
    return lead.phone or ""
