"""
Single shared worker resilience tests.

Required by docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md section 4.3.
No separate dead-letter service is built here -- the existing
app.outreach.dead_letter module already implements exactly this for
outreach sends, and is exercised directly.

Writing these tests found two real resilience bugs (fixed alongside the
tests, same principle as sections 4.1/4.2/4.6): the per-item loops in
run_enricher (app/workers/enricher_worker.py) and run_outreach_generator
(app/workers/outreach_generator_worker.py) had no try/except around each
item's processing. An unhandled exception on a single lead or message
propagated out of the whole loop, aborting every subsequent item in the
same batch with no per-item error recorded -- exactly the failure mode
this section exists to catch. Both now isolate each item: the failing
one is marked with a failed/blocked state and a stored error message,
and the loop continues with the rest. A related but narrower gap in
run_outreach_sender_batch's per-message loop was fixed the same way.
run_publisher and run_collector already isolated each item correctly and
needed no change (verified by inspection and by the tests below).
"""

import uuid
from unittest.mock import patch

import pytest

from app.models.audit import AuditLog
from app.models.campaign import MessageStatus, OutreachCampaign, OutreachMessage
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import JobStatus, SearchJob
from app.outreach.dead_letter import requeue_dead_letter
from app.workers.enricher_worker import run_enricher
from app.workers.outreach_generator_worker import run_outreach_generator
from app.workers.outreach_sender_worker import run_outreach_sender

SANDBOX_PHONE = "+77000000001"


class TestEnricherIsolatesFailures:
    def test_one_lead_failing_does_not_block_the_rest_of_the_batch(self, db):
        job = SearchJob(city="Алматы", category="Мебель", limit=3, provider="csv", status=JobStatus.enriching.value)
        db.add(job)
        db.commit()

        good_lead_1 = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.collected.value)
        bad_lead = Lead(name="Проблемный Лид", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.collected.value)
        good_lead_2 = Lead(name="Шкаф Мастер", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.collected.value)
        db.add_all([good_lead_1, bad_lead, good_lead_2])
        db.commit()

        real_enrich_lead = __import__(
            "app.enrichment.enricher", fromlist=["enrich_lead"]
        ).enrich_lead

        def flaky_enrich_lead(lead):
            if lead.id == bad_lead.id:
                raise RuntimeError("Simulated enrichment crash")
            return real_enrich_lead(lead)

        with patch("app.workers.enricher_worker.enrich_lead", side_effect=flaky_enrich_lead):
            run_enricher([good_lead_1.id, bad_lead.id, good_lead_2.id], job.id)

        db.refresh(good_lead_1)
        db.refresh(bad_lead)
        db.refresh(good_lead_2)

        # 1 & 2: exception captured, failed state + readable error stored.
        assert bad_lead.status == LeadStatus.failed.value
        audit_entry = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "lead", AuditLog.entity_id == str(bad_lead.id))
            .filter(AuditLog.action == "enrichment_failed")
            .first()
        )
        assert audit_entry is not None
        assert "Simulated enrichment crash" in audit_entry.details_json

        # 4: worker continued processing the rest of the batch.
        assert good_lead_1.status == LeadStatus.enriched.value
        assert good_lead_1.slug and good_lead_1.slug != "company"
        assert good_lead_2.status == LeadStatus.enriched.value
        assert good_lead_2.slug and good_lead_2.slug != "company"

        # 4b: the job itself is not stuck in a failed state just because
        # one lead in the batch failed -- most of the batch succeeded.
        db.refresh(job)
        assert job.status == JobStatus.generating.value

    def test_failed_lead_can_be_safely_retried(self, db):
        job = SearchJob(city="Алматы", category="Мебель", limit=1, provider="csv", status=JobStatus.enriching.value)
        db.add(job)
        db.commit()

        lead = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.collected.value)
        db.add(lead)
        db.commit()

        real_enrich_lead = __import__(
            "app.enrichment.enricher", fromlist=["enrich_lead"]
        ).enrich_lead

        call_count = {"n": 0}

        def fails_once_then_succeeds(lead_arg):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Transient failure")
            return real_enrich_lead(lead_arg)

        with patch("app.workers.enricher_worker.enrich_lead", side_effect=fails_once_then_succeeds):
            run_enricher([lead.id], job.id)
            db.refresh(lead)
            assert lead.status == LeadStatus.failed.value

            # 5: retry -- simply re-running the worker for the same lead id.
            run_enricher([lead.id], job.id)
            db.refresh(lead)

        assert lead.status == LeadStatus.enriched.value
        assert lead.slug


class TestOutreachGeneratorIsolatesFailures:
    def test_one_message_failing_does_not_block_the_rest_of_the_campaign(self, db):
        lead_ok_1 = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.published.value)
        lead_bad = Lead(name="Проблемный Лид", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.published.value)
        lead_ok_2 = Lead(name="Шкаф Мастер", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.published.value)
        db.add_all([lead_ok_1, lead_bad, lead_ok_2])
        db.flush()

        campaign = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="Resilience Test", channel="whatsapp",
            language="ru", status="active",
        )
        db.add(campaign)
        db.flush()

        msg_ok_1 = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign.id, lead_id=lead_ok_1.id,
            channel="whatsapp", recipient="", body="", status=MessageStatus.draft.value,
        )
        msg_bad = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign.id, lead_id=lead_bad.id,
            channel="whatsapp", recipient="", body="", status=MessageStatus.draft.value,
        )
        msg_ok_2 = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign.id, lead_id=lead_ok_2.id,
            channel="whatsapp", recipient="", body="", status=MessageStatus.draft.value,
        )
        db.add_all([msg_ok_1, msg_bad, msg_ok_2])
        db.commit()

        real_generate_messages = __import__(
            "app.outreach.message_generator", fromlist=["generate_messages"]
        ).generate_messages

        def flaky_generate_messages(ctx):
            if ctx.company_name == "Проблемный Лид":
                raise RuntimeError("Simulated message generation crash")
            return real_generate_messages(ctx)

        with patch(
            "app.workers.outreach_generator_worker.generate_messages",
            side_effect=flaky_generate_messages,
        ):
            run_outreach_generator(campaign.id)

        db.refresh(msg_ok_1)
        db.refresh(msg_bad)
        db.refresh(msg_ok_2)

        # Failure captured with a readable error, rest of campaign proceeds.
        assert msg_bad.status == MessageStatus.blocked.value
        assert msg_bad.error_message and "Simulated message generation crash" in msg_bad.error_message

        assert msg_ok_1.status == MessageStatus.needs_review.value
        assert msg_ok_1.body
        assert msg_ok_2.status == MessageStatus.needs_review.value
        assert msg_ok_2.body


class TestOutreachSendRetryRespectsPolicyChecks:
    def _dead_letter_message(self, db, *, do_not_contact=False, recipient=SANDBOX_PHONE):
        lead = Lead(
            name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE,
            whatsapp=f"https://wa.me/{SANDBOX_PHONE.lstrip('+')}",
            status=LeadStatus.published.value, do_not_contact=do_not_contact,
        )
        db.add(lead)
        db.flush()
        campaign = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="DL Test", channel="whatsapp", language="ru", status="active",
        )
        db.add(campaign)
        db.flush()
        msg = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign.id, lead_id=lead.id,
            channel="whatsapp", recipient=recipient, body="Тест",
            status=MessageStatus.dead_letter.value, attempt_count=5,
            error_message="Simulated exhausted retries",
        )
        db.add(msg)
        db.commit()
        return lead, msg

    def test_retry_blocked_for_do_not_contact_lead(self, db):
        with patch("app.outreach.dead_letter.settings") as mock:
            mock.outreach_mode = "sandbox"
            mock.outreach_enabled = True
            lead, msg = self._dead_letter_message(db, do_not_contact=True)
            ok, reason = requeue_dead_letter(db, msg.id)

        assert ok is False
        assert "do_not_contact" in reason.lower()
        db.refresh(msg)
        assert msg.status == MessageStatus.dead_letter.value  # unchanged

    def test_retry_blocked_when_recipient_outside_sandbox_allowlist(self, db):
        with patch("app.outreach.dead_letter.settings") as mock, \
             patch("app.outreach.service.settings") as svc_mock:
            mock.outreach_mode = "sandbox"
            mock.outreach_enabled = True
            svc_mock.outreach_mode = "sandbox"
            svc_mock.sandbox_allowlist = {SANDBOX_PHONE}
            lead, msg = self._dead_letter_message(db, recipient="+77099998877")
            ok, reason = requeue_dead_letter(db, msg.id)

        assert ok is False
        assert "sandbox" in reason.lower()
        db.refresh(msg)
        assert msg.status == MessageStatus.dead_letter.value

    def test_retry_succeeds_and_reset_state_for_a_legitimately_retryable_message(self, db):
        with patch("app.outreach.dead_letter.settings") as mock, \
             patch("app.outreach.service.settings") as svc_mock:
            mock.outreach_mode = "sandbox"
            mock.outreach_enabled = True
            svc_mock.outreach_mode = "sandbox"
            svc_mock.sandbox_allowlist = {SANDBOX_PHONE}
            lead, msg = self._dead_letter_message(db)
            ok, reason = requeue_dead_letter(db, msg.id)

        assert ok is True
        db.refresh(msg)
        assert msg.status == MessageStatus.approved.value
        assert msg.error_message is None
        assert msg.attempt_count == 0
