"""
Idempotency and duplicate-protection regression tests.

Required by docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md section 4.2.
Uses existing database constraints, current identifiers, and small
targeted guards -- no new generalized idempotency framework, per the
doc's explicit instruction.

Covers, in order:
  - importing the same source lead twice
  - enriching the same lead twice
  - generating content twice for the same lead
  - publishing the same approved landing twice
  - pressing send twice on the same message
  - running the sender job twice
  - receiving the same webhook event twice
  - retrying after a failure doesn't create an unrelated entity

Writing the "generate content twice" test found a real gap: POST
/leads/{id}/content-generations had no guard at all against being called
twice for the same lead. Since a landing's slug comes from the lead (not
the generation), two calls would create two ContentGeneration rows and
two competing LandingPage rows sharing the same slug -- both could end
up marked "published" in the database while only one directory actually
exists on disk (publish_site() uses the slug as the folder name). Fixed
with a minimal guard in the route: block a second request while one is
already in flight (queued/running), and reuse the lead's existing
landing on a fresh/regenerate request instead of creating a competing one.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.campaign import MessageStatus, OutreachCampaign, OutreachMessage
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import LandingPage, LandingStatus, ReviewStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import JobStatus, SearchJob
from app.models.whatsapp import InboundMessage
from app.workers.collector_worker import run_collector
from app.workers.content_generator_worker import run_content_generator
from app.workers.enricher_worker import run_enricher
from app.workers.outreach_sender_worker import run_outreach_sender
from app.workers.publisher_worker import run_publisher

SANDBOX_PHONE = "+77000000001"


@pytest.fixture
def client():
    return TestClient(app)


def _patch_outreach_settings(mock):
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


class TestImportIdempotency:
    def test_running_collector_twice_does_not_duplicate_leads(self, db):
        # run_collector enqueues an enrich job over Redis when it finds new
        # leads; not exercising that here, only the collection/dedup logic.
        with patch("app.workers.collector_worker.redis_conn"), \
             patch("rq.Queue.enqueue", return_value=None):
            job1 = SearchJob(city="Алматы", category="Мебель на заказ", limit=20, provider="mock")
            db.add(job1)
            db.commit()
            run_collector(job1.id)

            count_after_first = db.query(Lead).filter(Lead.source == "mock").count()
            assert count_after_first > 0

            job2 = SearchJob(city="Алматы", category="Мебель на заказ", limit=20, provider="mock")
            db.add(job2)
            db.commit()
            run_collector(job2.id)

            count_after_second = db.query(Lead).filter(Lead.source == "mock").count()

        assert count_after_second == count_after_first


class TestEnrichmentIdempotency:
    def test_enriching_same_lead_twice_produces_same_slug(self, db):
        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            category="Мебель на заказ",
            phone=SANDBOX_PHONE,
            status=LeadStatus.collected.value,
        )
        db.add(lead)
        db.commit()

        run_enricher([lead.id], job_id=self._make_job(db))
        db.refresh(lead)
        first_slug = lead.slug

        run_enricher([lead.id], job_id=self._make_job(db))
        db.refresh(lead)
        second_slug = lead.slug

        assert first_slug == second_slug
        assert first_slug != "company"

    @staticmethod
    def _make_job(db):
        job = SearchJob(city="Алматы", category="Мебель", limit=1, provider="csv", status=JobStatus.enriching.value)
        db.add(job)
        db.commit()
        return job.id


class TestContentGenerationIdempotency:
    def test_second_request_blocked_while_first_in_flight(self, client, db):
        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            phone=SANDBOX_PHONE,
            slug="almaty-derevo-master-1",
            status=LeadStatus.enriched.value,
        )
        db.add(lead)
        db.commit()

        with patch("rq.Queue.enqueue", return_value=None):
            resp1 = client.post(f"/leads/{lead.id}/content-generations")
            assert resp1.status_code == 200

            resp2 = client.post(f"/leads/{lead.id}/content-generations")
        assert resp2.status_code == 409

        generations = (
            db.query(ContentGeneration).filter(ContentGeneration.lead_id == lead.id).all()
        )
        assert len(generations) == 1

    def test_regenerate_after_success_reuses_existing_landing(self, client, db):
        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            phone=SANDBOX_PHONE,
            slug="almaty-derevo-master-2",
            status=LeadStatus.enriched.value,
        )
        db.add(lead)
        db.commit()

        gen1 = ContentGeneration(
            id=str(uuid.uuid4())[:12],
            lead_id=lead.id,
            provider="mock",
            prompt_version="v1",
            status=ContentGenerationStatus.queued.value,
            language="ru",
        )
        db.add(gen1)
        db.commit()
        run_content_generator(gen1.id)
        db.refresh(gen1)
        assert gen1.status == ContentGenerationStatus.succeeded.value
        first_landing_id = gen1.landing_page_id

        # Now the first generation is terminal (succeeded), so a second
        # request is allowed through -- it must reuse the same landing.
        with patch("rq.Queue.enqueue", return_value=None):
            resp = client.post(f"/leads/{lead.id}/content-generations")
        assert resp.status_code == 200
        gen2_id = resp.json()["id"]

        run_content_generator(gen2_id)

        landings = db.query(LandingPage).filter(LandingPage.lead_id == lead.id).all()
        assert len(landings) == 1
        assert landings[0].id == first_landing_id


class TestPublishIdempotency:
    def test_publishing_same_landing_twice_is_safe(self, db, tmp_path):
        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            phone=SANDBOX_PHONE,
            slug="almaty-derevo-master-3",
            status=LeadStatus.enriched.value,
        )
        db.add(lead)
        db.commit()

        job = SearchJob(city="Алматы", category="Мебель", limit=1, provider="csv", status=JobStatus.enriching.value)
        db.add(job)
        db.commit()

        gen = ContentGeneration(
            id=str(uuid.uuid4())[:12],
            lead_id=lead.id,
            provider="mock",
            prompt_version="v1",
            status=ContentGenerationStatus.queued.value,
            language="ru",
        )
        db.add(gen)
        db.commit()
        run_content_generator(gen.id)
        db.refresh(gen)

        landing = db.query(LandingPage).filter(LandingPage.id == gen.landing_page_id).first()
        landing.review_status = ReviewStatus.approved.value
        db.commit()

        with patch("app.landing.renderer.SITES_DIR", tmp_path / "sites"), \
             patch("app.publisher.publisher.SITES_DIR", tmp_path / "sites"):
            run_publisher([landing.id], job.id)
            db.refresh(landing)
            assert landing.status == LandingStatus.published.value

            # Publish again -- must not raise or corrupt the output.
            run_publisher([landing.id], job.id)
            db.refresh(landing)
            assert landing.status == LandingStatus.published.value

            published_dir = tmp_path / "sites" / "public" / landing.slug
            assert (published_dir / "index.html").exists()


class TestSendIdempotency:
    def _make_sent_ready_message(self, db):
        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            phone=SANDBOX_PHONE,
            whatsapp=f"https://wa.me/{SANDBOX_PHONE.lstrip('+')}",
            status=LeadStatus.enriched.value,
        )
        db.add(lead)
        db.flush()
        campaign = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="Test", channel="whatsapp", language="ru", status="active"
        )
        db.add(campaign)
        db.flush()
        msg = OutreachMessage(
            id=str(uuid.uuid4())[:12],
            campaign_id=campaign.id,
            lead_id=lead.id,
            channel="whatsapp",
            recipient=lead.whatsapp,
            body="Тест",
            status=MessageStatus.approved.value,
        )
        db.add(msg)
        db.commit()
        return msg

    def test_pressing_send_twice_is_rejected_the_second_time(self, client, db):
        msg = self._make_sent_ready_message(db)

        with patch("rq.Queue.enqueue", return_value=None), \
             patch("app.api.outreach_routes.settings") as route_settings:
            route_settings.outreach_enabled = True
            resp1 = client.post(f"/outreach-messages/{msg.id}/send")
            assert resp1.status_code == 200

            resp2 = client.post(f"/outreach-messages/{msg.id}/send")
        # Second call must not silently re-send: status is no longer 'approved'.
        assert resp2.status_code == 400

    def test_running_sender_worker_twice_does_not_resend(self, db):
        msg = self._make_sent_ready_message(db)

        with patch("app.outreach.service.settings") as svc, \
             patch("app.workers.outreach_sender_worker.settings") as worker_settings:
            _patch_outreach_settings(svc)
            _patch_outreach_settings(worker_settings)
            run_outreach_sender(msg.id)
            db.refresh(msg)
            assert msg.status == MessageStatus.sent.value
            first_provider_id = msg.provider_message_id

            # Re-running the worker on an already-sent message must not
            # send again or replace the provider_message_id.
            run_outreach_sender(msg.id)
            db.refresh(msg)

        assert msg.status == MessageStatus.sent.value
        assert msg.provider_message_id == first_provider_id


class TestWebhookIdempotency:
    def test_same_inbound_webhook_processed_once(self, client, db):
        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            phone=SANDBOX_PHONE,
            status=LeadStatus.published.value,
        )
        db.add(lead)
        db.commit()

        provider_id = f"wamid.idem_{uuid.uuid4().hex[:8]}"
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": provider_id,
                                        "from": SANDBOX_PHONE.lstrip("+"),
                                        "type": "text",
                                        "text": {"body": "Здравствуйте"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        resp1 = client.post("/webhooks/whatsapp", json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["changed"] == 1

        resp2 = client.post("/webhooks/whatsapp", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["changed"] == 0

        count = (
            db.query(InboundMessage)
            .filter(InboundMessage.provider_message_id == provider_id)
            .count()
        )
        assert count == 1


class TestRetryDoesNotCreateUnrelatedEntity:
    def test_regenerating_after_a_failed_generation_reuses_the_lead_landing(self, client, db):
        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            phone=SANDBOX_PHONE,
            slug="almaty-derevo-master-4",
            status=LeadStatus.enriched.value,
        )
        db.add(lead)
        db.commit()

        # Simulate a first generation that failed outright (e.g. provider
        # error) -- no landing was ever created for it.
        failed_gen = ContentGeneration(
            id=str(uuid.uuid4())[:12],
            lead_id=lead.id,
            provider="mock",
            prompt_version="v1",
            status=ContentGenerationStatus.failed.value,
            error_message="Simulated provider failure",
            language="ru",
        )
        db.add(failed_gen)
        db.commit()

        # Retry: create a fresh generation through the real endpoint and
        # actually run it.
        with patch("rq.Queue.enqueue", return_value=None):
            resp = client.post(f"/leads/{lead.id}/content-generations")
        assert resp.status_code == 200
        retry_gen_id = resp.json()["id"]
        assert retry_gen_id != failed_gen.id

        run_content_generator(retry_gen_id)

        landings = db.query(LandingPage).filter(LandingPage.lead_id == lead.id).all()
        assert len(landings) == 1
