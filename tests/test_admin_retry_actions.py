"""
Admin retry action tests.

Required by docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md section 4.4.
Uses the existing admin UI, existing auth (admin_auth cookie) and CSRF
protection, POST-only actions, and existing audit facilities. No new
dashboard.

Writing these tests found and fixed two real gaps:

- POST /landings/{id}/publish (the actual endpoint the MVP flow uses,
  not the job-based run_publisher worker) had no exception handling at
  all around rendering/saving/publishing. A failure there was an
  unhandled exception -- a raw 500 with the landing left in 'approved'
  status forever, no readable error stored anywhere, and therefore
  nothing for this admin retry action (or an operator) to even detect as
  failed. Fixed to mirror run_publisher's defensive per-step handling:
  on failure the landing is marked 'failed' with review_note set to a
  readable error.

- run_enricher() silently no-op'd for a lead with no search_job_id
  (`if not job: return` before touching any lead), which is exactly the
  situation for a single-lead admin retry outside of a batch collection
  job. Fixed to make the SearchJob lookup optional so single-lead
  retries actually run.

Also confirms, per the doc's explicit requirement: no retry action is
offered for messages in 'blocked' status (permanent policy blocks --
DNC, sandbox mismatch, invalid recipient) or for dead_letter messages
with retryable=False.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.campaign import MessageStatus, OutreachCampaign, OutreachMessage
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import LandingPage, LandingStatus, ReviewStatus
from app.models.lead import Lead, LeadStatus
from app.security import generate_csrf_token

SANDBOX_PHONE = "+77000000001"
ADMIN_COOKIES = {"admin_auth": "testpass"}  # matches conftest's ADMIN_PASSWORD


@pytest.fixture
def client():
    return TestClient(app, cookies=ADMIN_COOKIES)


class TestRetryEnrichmentAction:
    def test_retry_button_only_shown_for_failed_leads(self, client, db):
        ok_lead = Lead(name="ОК Лид", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.enriched.value)
        failed_lead = Lead(name="Проблемный Лид", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.failed.value)
        db.add_all([ok_lead, failed_lead])
        db.commit()

        resp = client.get("/admin/leads")
        assert resp.status_code == 200
        assert f"/admin/leads/{failed_lead.id}/retry-enrichment" in resp.text
        assert f"/admin/leads/{ok_lead.id}/retry-enrichment" not in resp.text

    def test_retry_enrichment_succeeds_for_failed_lead(self, client, db):
        lead = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.failed.value)
        db.add(lead)
        db.commit()

        csrf = generate_csrf_token()
        resp = client.post(
            f"/admin/leads/{lead.id}/retry-enrichment",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "retry=ok" in resp.headers["location"]

        db.refresh(lead)
        assert lead.status == LeadStatus.enriched.value
        assert lead.slug and lead.slug != "company"

    def test_retry_enrichment_rejected_for_non_failed_lead(self, client, db):
        lead = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.enriched.value)
        db.add(lead)
        db.commit()

        csrf = generate_csrf_token()
        resp = client.post(
            f"/admin/leads/{lead.id}/retry-enrichment",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert "retry=error" in resp.headers["location"]

    def test_retry_enrichment_requires_valid_csrf(self, client, db):
        lead = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, status=LeadStatus.failed.value)
        db.add(lead)
        db.commit()

        resp = client.post(
            f"/admin/leads/{lead.id}/retry-enrichment",
            data={"csrf_token": "not-a-real-token"},
        )
        assert resp.status_code == 403


class TestRetryContentGenerationAction:
    def test_retry_shown_only_when_last_generation_failed(self, client, db):
        lead = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, slug="almaty-derevo-master-1", status=LeadStatus.enriched.value)
        db.add(lead)
        db.commit()

        gen = ContentGeneration(
            id=str(uuid.uuid4())[:12], lead_id=lead.id, provider="mock",
            prompt_version="v1", status=ContentGenerationStatus.failed.value,
            error_message="Simulated failure", language="ru",
        )
        db.add(gen)
        db.commit()

        resp = client.get(f"/admin/leads/{lead.id}")
        assert resp.status_code == 200
        assert f"/admin/leads/{lead.id}/retry-content-generation" in resp.text

    def test_retry_content_generation_succeeds(self, client, db):
        lead = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, slug="almaty-derevo-master-2", status=LeadStatus.enriched.value)
        db.add(lead)
        db.commit()

        gen = ContentGeneration(
            id=str(uuid.uuid4())[:12], lead_id=lead.id, provider="mock",
            prompt_version="v1", status=ContentGenerationStatus.failed.value,
            error_message="Simulated failure", language="ru",
        )
        db.add(gen)
        db.commit()

        csrf = generate_csrf_token()
        resp = client.post(
            f"/admin/leads/{lead.id}/retry-content-generation",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert "retry=ok" in resp.headers["location"]

        landings = db.query(LandingPage).filter(LandingPage.lead_id == lead.id).all()
        assert len(landings) == 1
        assert landings[0].review_status == ReviewStatus.needs_review.value


class TestRetryPublishAction:
    def test_retry_button_only_shown_for_failed_approved_landing(self, client, db, tmp_path):
        lead = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, slug="almaty-derevo-master-3", status=LeadStatus.enriched.value)
        db.add(lead)
        db.commit()

        landing = LandingPage(
            id=str(uuid.uuid4())[:12], lead_id=lead.id, slug=lead.slug,
            title="Test", profile_json='{"company": {"name": "Test"}}',
            status=LandingStatus.failed.value, review_status=ReviewStatus.approved.value,
        )
        db.add(landing)
        db.commit()

        resp = client.get(f"/admin/landings/{landing.id}")
        assert resp.status_code == 200
        assert f"/admin/landings/{landing.id}/retry-publish" in resp.text

    def test_retry_publish_succeeds(self, client, db, tmp_path):
        from unittest.mock import patch

        lead = Lead(name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE, slug="almaty-derevo-master-4", status=LeadStatus.enriched.value)
        db.add(lead)
        db.commit()

        profile_json = (
            '{"company": {"name": "Дерево Мастер", "city": "Алматы"}, '
            '"hero": {"title": "T", "subtitle": "S", "cta_text": "CTA"}, "services": [], '
            '"advantages": [], "contacts": {"phone": "+77000000001"}, '
            '"meta": {"title": "T", "description": "D"}}'
        )
        landing = LandingPage(
            id=str(uuid.uuid4())[:12], lead_id=lead.id, slug=lead.slug,
            title="Test", profile_json=profile_json,
            status=LandingStatus.failed.value, review_status=ReviewStatus.approved.value,
        )
        db.add(landing)
        db.commit()

        csrf = generate_csrf_token()
        with patch("app.landing.renderer.SITES_DIR", tmp_path / "sites"), \
             patch("app.publisher.publisher.SITES_DIR", tmp_path / "sites"):
            resp = client.post(
                f"/admin/landings/{landing.id}/retry-publish",
                data={"csrf_token": csrf},
                follow_redirects=False,
            )

        assert "retry=ok" in resp.headers["location"]
        db.refresh(landing)
        assert landing.status == LandingStatus.published.value


class TestRetrySendAction:
    def _dead_letter_message(self, db, *, retryable=True):
        lead = Lead(
            name="Дерево Мастер", city="Алматы", phone=SANDBOX_PHONE,
            whatsapp=f"https://wa.me/{SANDBOX_PHONE.lstrip('+')}",
            status=LeadStatus.published.value,
        )
        db.add(lead)
        db.flush()
        campaign = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="Test", channel="whatsapp", language="ru", status="active",
        )
        db.add(campaign)
        db.flush()
        msg = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign.id, lead_id=lead.id,
            channel="whatsapp", recipient=lead.whatsapp, body="Тест",
            status=MessageStatus.dead_letter.value, retryable=retryable, attempt_count=5,
            error_message="Simulated exhausted retries",
        )
        db.add(msg)
        db.commit()
        return msg

    def test_retry_button_shown_only_for_retryable_dead_letter(self, client, db):
        retryable_msg = self._dead_letter_message(db, retryable=True)
        blocked_msg = self._dead_letter_message(db, retryable=False)

        resp = client.get("/admin/messages")
        assert resp.status_code == 200
        assert f"/admin/messages/{retryable_msg.id}/retry-send" in resp.text
        assert f"/admin/messages/{blocked_msg.id}/retry-send" not in resp.text

    def test_retry_send_succeeds_with_full_policy_checks(self, client, db):
        from unittest.mock import patch

        msg = self._dead_letter_message(db, retryable=True)

        with patch("app.outreach.dead_letter.settings") as dl_settings, \
             patch("app.outreach.service.settings") as svc_settings, \
             patch("app.workers.outreach_sender_worker.settings") as worker_settings:
            for mock in (dl_settings, svc_settings, worker_settings):
                mock.outreach_mode = "sandbox"
                mock.outreach_enabled = True
                mock.sandbox_allowlist = {SANDBOX_PHONE}
                mock.outreach_timezone = "Asia/Almaty"
                mock.outreach_quiet_hours_start = "00:00"
                mock.outreach_quiet_hours_end = "00:00"
                mock.outreach_max_per_hour = 1000
                mock.outreach_provider = "mock"
                mock.outreach_send_max_retries = 5
                mock.outreach_send_retry_base_seconds = 30

            csrf = generate_csrf_token()
            resp = client.post(
                f"/admin/messages/{msg.id}/retry-send",
                data={"csrf_token": csrf},
                follow_redirects=False,
            )

        assert "retry=ok" in resp.headers["location"]
        db.refresh(msg)
        assert msg.status == MessageStatus.sent.value
        assert msg.provider_message_id
