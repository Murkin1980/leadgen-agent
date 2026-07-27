"""
True end-to-end MVP pipeline test.

Required by docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md section 4.1.

Exercises the real application services and worker functions for the full
flow:

    import lead -> enrich -> generate content -> approve -> publish
    -> create outreach message -> approve -> send -> receive webhook

Calls actual worker functions (run_enricher, run_content_generator,
run_publisher, run_outreach_generator, run_outreach_sender) rather than
only checking that an RQ job was enqueued -- the earlier test suite's main
gap, per the same doc's section 3. Steps that don't have a "worker
function" of their own (approve, publish-trigger via job scheduling,
webhook receipt) go through the real FastAPI TestClient so the API
service layer itself is exercised too.

Writes landing files to a temporary directory rather than the real
sites/public, by patching the SITES_DIR module constant (there's no
settings knob for it -- see app/publisher/publisher.py and
app/landing/renderer.py). Avoids any live Redis dependency: run_collector
and the /generate-messages, /outreach-messages/{id}/send API endpoints
enqueue RQ jobs, but the worker functions used here don't need a live
Redis connection on the success path (only the retry-scheduling path in
run_outreach_sender does, and that's not exercised by a clean send).
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.campaign import MessageStatus, OutreachCampaign, OutreachMessage
from app.models.lead import Lead, LeadStatus
from app.models.landing_page import LandingPage, ReviewStatus, LandingStatus
from app.models.search_job import SearchJob, JobStatus
from app.models.whatsapp import InboundMessage
from app.workers.content_generator_worker import run_content_generator
from app.workers.enricher_worker import run_enricher
from app.workers.outreach_generator_worker import run_outreach_generator
from app.workers.outreach_sender_worker import run_outreach_sender
from app.workers.publisher_worker import run_publisher

SANDBOX_PHONE = "+77000000001"  # matches conftest's OUTREACH_SANDBOX_ALLOWLIST


@pytest.fixture
def client():
    return TestClient(app)


def _patch_outreach_settings(mock):
    """Common settings needed to let a sandbox send actually go through."""
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


class TestMvpPipelineEndToEnd:
    def test_full_pipeline_import_to_webhook_reply(self, client, db, tmp_path):
        # ── 1. Create/import one lead ────────────────────────────────
        job = SearchJob(
            city="Алматы",
            category="Мебель на заказ",
            limit=1,
            provider="csv",
            status=JobStatus.enriching.value,
        )
        db.add(job)
        db.flush()

        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            category="Мебель на заказ",
            phone=SANDBOX_PHONE,
            website=None,
            has_website=False,
            status=LeadStatus.collected.value,
            search_job_id=job.id,
        )
        db.add(lead)
        db.commit()
        lead_id = lead.id

        # ── 2. Enrich the lead (real worker function) ───────────────
        run_enricher([lead_id], job.id)

        db.refresh(lead)
        assert lead.status == LeadStatus.enriched.value

        # ── 3. Verify a unique slug is generated ────────────────────
        assert lead.slug
        assert lead.slug != "company"
        assert lead.slug.endswith(f"-{lead_id}")
        assert lead.whatsapp is not None

        # ── 4. Run content generation through the actual worker ────
        gen_id = str(uuid.uuid4())[:12]
        from app.models.content_generation import ContentGeneration, ContentGenerationStatus

        gen = ContentGeneration(
            id=gen_id,
            lead_id=lead_id,
            provider="mock",
            prompt_version="v1",
            status=ContentGenerationStatus.queued.value,
            language="ru",
        )
        db.add(gen)
        db.commit()

        run_content_generator(gen_id)

        db.refresh(gen)
        assert gen.status == ContentGenerationStatus.succeeded.value, gen.error_message

        # ── 5. Verify the landing record is created ─────────────────
        landing = (
            db.query(LandingPage).filter(LandingPage.id == gen.landing_page_id).first()
        )
        assert landing is not None
        assert landing.review_status == ReviewStatus.needs_review.value
        assert landing.slug == lead.slug

        # ── 6. Approve the landing (through the real API) ──────────
        resp = client.post(f"/landings/{landing.id}/approve")
        assert resp.status_code == 200, resp.text
        assert resp.json()["review_status"] == "approved"

        # ── 7. Run the publish worker (real worker function) ───────
        drafts_dir = tmp_path / "sites" / "drafts"
        public_dir = tmp_path / "sites" / "public"
        with patch("app.landing.renderer.SITES_DIR", tmp_path / "sites"), \
             patch("app.publisher.publisher.SITES_DIR", tmp_path / "sites"):
            run_publisher([landing.id], job.id)

            db.refresh(landing)
            assert landing.status == LandingStatus.published.value, landing.output_path
            assert landing.review_status == ReviewStatus.published.value
            assert landing.preview_url

            # ── 8. Verify the expected files exist ──────────────────
            published_dir = public_dir / landing.slug
            assert (published_dir / "index.html").exists()
            assert (published_dir / "profile.json").exists()
            assert (published_dir / "styles.css").exists()
            html = (published_dir / "index.html").read_text(encoding="utf-8")
            assert lead.name in html

        db.refresh(lead)
        assert lead.status == LeadStatus.published.value

        # ── 9. Create an outreach campaign and message ──────────────
        campaign = OutreachCampaign(
            id=str(uuid.uuid4())[:12],
            name="E2E Test Campaign",
            channel="whatsapp",
            language="ru",
            status="active",
        )
        db.add(campaign)
        db.flush()

        msg = OutreachMessage(
            id=str(uuid.uuid4())[:12],
            campaign_id=campaign.id,
            lead_id=lead_id,
            channel="whatsapp",
            recipient="",
            body="",
            status=MessageStatus.draft.value,
        )
        db.add(msg)
        db.commit()

        run_outreach_generator(campaign.id)

        db.refresh(msg)
        assert msg.status == MessageStatus.needs_review.value, msg.error_message
        assert msg.body
        assert landing.slug in msg.body or (landing.preview_url or "") in msg.body
        assert msg.recipient

        # ── 10. Approve the message (through the real API) ─────────
        resp = client.post(f"/outreach-messages/{msg.id}/approve")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "approved"

        # ── 11. Run the outreach sender worker with mock provider ──
        with patch("app.outreach.service.settings") as svc_settings, \
             patch("app.workers.outreach_sender_worker.settings") as worker_settings:
            _patch_outreach_settings(svc_settings)
            _patch_outreach_settings(worker_settings)
            run_outreach_sender(msg.id)

        # ── 12. Verify message becomes sent with a provider id ──────
        db.refresh(msg)
        assert msg.status == MessageStatus.sent.value, msg.error_message
        assert msg.provider_message_id

        # ── 13. Process a mock inbound webhook ──────────────────────
        provider_msg_id = f"wamid.e2e_{uuid.uuid4().hex[:8]}"
        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": provider_msg_id,
                                        "from": SANDBOX_PHONE.lstrip("+"),
                                        "type": "text",
                                        "text": {"body": "Да, интересно"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        resp = client.post("/webhooks/whatsapp", json=webhook_payload)
        assert resp.status_code == 200, resp.text
        assert resp.json()["changed"] == 1

        # ── 14. Verify the webhook is stored once ───────────────────
        inbound_count = (
            db.query(InboundMessage)
            .filter(InboundMessage.provider_message_id == provider_msg_id)
            .count()
        )
        assert inbound_count == 1

        # ── 15. Verify related message/lead state changes ──────────
        db.refresh(lead)
        assert lead.stage == "replied"
        assert lead.last_inbound_at is not None
