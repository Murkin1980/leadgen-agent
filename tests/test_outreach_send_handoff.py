"""
Regression coverage for the outreach send flow.

The /outreach-messages/{id}/send endpoint transitions a message from
'approved' to 'queued' *before* enqueuing the RQ job (so a message can't be
double-sent by a concurrent request). The worker (run_outreach_sender) then
calls can_send_message() to decide whether it's still safe to actually send.

can_send_message() used to only accept status == 'approved', so by the time
the worker ran -- which is always, since the endpoint already moved the
status to 'queued' -- every real send was rejected with "must be
'approved'" and the message ended up 'blocked'. This made the WhatsApp send
step of the pipeline non-functional 100% of the time.

No existing test exercised the endpoint's status transition together with
the worker's precondition check, which is exactly why this shipped.
"""

import uuid
from unittest.mock import patch

from app.models.campaign import MessageStatus, OutreachCampaign, OutreachMessage
from app.models.lead import Lead, LeadStatus
from app.outreach.service import can_send_message
from app.workers.outreach_sender_worker import run_outreach_sender

SANDBOX_PHONE = "+77000000001"  # matches conftest's OUTREACH_SANDBOX_ALLOWLIST


def _make_lead_campaign_message(db, status: str):
    lead = Lead(
        name="Sandbox Co",
        city="Алматы",
        phone=SANDBOX_PHONE,
        whatsapp=f"https://wa.me/{SANDBOX_PHONE.lstrip('+')}",
        status=LeadStatus.enriched.value,
        stage="ready_for_outreach",
    )
    db.add(lead)
    db.flush()

    campaign = OutreachCampaign(
        id=str(uuid.uuid4())[:12],
        name="Sandbox Test",
        channel="whatsapp",
        language="ru",
        status="active",
    )
    db.add(campaign)
    db.flush()

    msg = OutreachMessage(
        id=str(uuid.uuid4())[:12],
        campaign_id=campaign.id,
        lead_id=lead.id,
        channel="whatsapp",
        recipient=lead.whatsapp,
        body="Здравствуйте! Тест.",
        status=status,
    )
    db.add(msg)
    db.commit()
    return lead, campaign, msg


class TestSendEndpointWorkerHandoff:
    def _patched_settings(self, mock):
        mock.outreach_enabled = True
        mock.outreach_mode = "sandbox"
        mock.sandbox_allowlist = {SANDBOX_PHONE}
        mock.outreach_timezone = "Asia/Almaty"
        mock.outreach_quiet_hours_start = "00:00"
        mock.outreach_quiet_hours_end = "00:00"
        mock.outreach_max_per_hour = 1000
        mock.outreach_provider = "mock"
        mock.outreach_send_max_retries = 5
        mock.outreach_send_retry_base_seconds = 30

    def test_queued_message_can_still_be_sent(self, db):
        # Simulate exactly what the /send endpoint does: flip approved -> queued
        # before the worker ever looks at it.
        _, _, msg = _make_lead_campaign_message(db, MessageStatus.queued.value)

        with (
            patch("app.outreach.service.settings") as mock_service_settings,
            patch(
                "app.workers.outreach_sender_worker.settings"
            ) as mock_worker_settings,
        ):
            self._patched_settings(mock_service_settings)
            self._patched_settings(mock_worker_settings)
            run_outreach_sender(msg.id)

        db.refresh(msg)
        assert msg.status == MessageStatus.sent.value, msg.error_message
        assert msg.provider_message_id is not None

    def test_retrying_message_can_still_be_sent(self, db):
        _, _, msg = _make_lead_campaign_message(db, MessageStatus.retrying.value)

        with (
            patch("app.outreach.service.settings") as mock_service_settings,
            patch(
                "app.workers.outreach_sender_worker.settings"
            ) as mock_worker_settings,
        ):
            self._patched_settings(mock_service_settings)
            self._patched_settings(mock_worker_settings)
            run_outreach_sender(msg.id)

        db.refresh(msg)
        assert msg.status == MessageStatus.sent.value, msg.error_message

    def test_draft_message_is_still_rejected(self, db):
        # Make sure loosening the check didn't open the door to sending
        # messages that were never approved at all.
        _, _, msg = _make_lead_campaign_message(db, MessageStatus.draft.value)

        with patch("app.outreach.service.settings") as mock:
            self._patched_settings(mock)
            ok, reason = can_send_message(msg)

        assert ok is False
        assert "approved" in reason
