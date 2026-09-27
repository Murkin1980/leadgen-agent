"""Worker-level MVP pipeline integration coverage.

Unlike ``test_mvp_flow.py``, this test calls the real generation, publication,
outreach and webhook code paths instead of manually assigning success states.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models.campaign import (
    CampaignStatus,
    MessageStatus,
    OutreachCampaign,
    OutreachMessage,
)
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import LandingPage, LandingStatus, ReviewStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import JobStatus, SearchJob
from app.models.stage import LeadStage
from app.models.whatsapp import InboundMessage
from app.security import generate_csrf_token
from app.workers.content_generator_worker import run_content_generator
from app.workers.outreach_sender_worker import run_outreach_sender
from app.workers.publisher_worker import run_publisher

SANDBOX_PHONE = "+77000000001"


def _patch_outreach_settings(mock_settings, sandbox_phone: str = SANDBOX_PHONE) -> None:
    mock_settings.outreach_enabled = True
    mock_settings.outreach_mode = "sandbox"
    mock_settings.sandbox_allowlist = {sandbox_phone}
    mock_settings.outreach_timezone = "Asia/Almaty"
    mock_settings.outreach_quiet_hours_start = "00:00"
    mock_settings.outreach_quiet_hours_end = "00:00"
    mock_settings.outreach_max_per_hour = 1000
    mock_settings.outreach_provider = "mock"
    mock_settings.outreach_send_max_retries = 2
    mock_settings.outreach_send_retry_base_seconds = 1


def test_real_worker_mvp_pipeline(db, tmp_path, monkeypatch):
    """One lead completes generation -> publish -> send -> inbound reply."""
    from app.landing import renderer
    from app.outreach import service as outreach_service
    from app.publisher import publisher
    from app.workers import outreach_sender_worker

    sites_dir = tmp_path / "sites"
    sandbox_phone = f"+77{uuid.uuid4().int % 900_000_000 + 100_000_000}"
    monkeypatch.setattr(renderer, "SITES_DIR", sites_dir)
    monkeypatch.setattr(publisher, "SITES_DIR", sites_dir)

    lead = Lead(
        name="ТОО «Құрылыс Жиһаз»",
        city="Алматы",
        category="Мебель на заказ",
        phone=sandbox_phone,
        whatsapp=sandbox_phone,
        slug=f"almaty-qurylys-zhihaz-{uuid.uuid4().hex[:6]}",
        status=LeadStatus.enriched.value,
        stage=LeadStage.new.value,
        qualification_score=90,
    )
    db.add(lead)
    db.flush()

    job = SearchJob(
        city="Алматы",
        category="Мебель на заказ",
        provider="mock",
        status=JobStatus.pending.value,
        limit=1,
    )
    db.add(job)
    db.flush()

    generation = ContentGeneration(
        id=f"gen_{uuid.uuid4().hex[:12]}",
        lead_id=lead.id,
        provider="template",
        prompt_version="v1",
        status=ContentGenerationStatus.queued.value,
        language="ru",
    )
    db.add(generation)
    db.commit()

    run_content_generator(generation.id)

    db.expire_all()
    generation = db.query(ContentGeneration).filter_by(id=generation.id).one()
    assert generation.status == ContentGenerationStatus.succeeded.value
    assert generation.landing_page_id

    landing = db.query(LandingPage).filter_by(id=generation.landing_page_id).one()
    assert landing.review_status == ReviewStatus.needs_review.value
    assert landing.slug == lead.slug

    landing_approval = TestClient(app).post(
        f"/admin/landings/{landing.id}/approve",
        data={"csrf_token": generate_csrf_token()},
        cookies={"admin_auth": "testpass"},
        follow_redirects=False,
    )
    assert landing_approval.status_code == 302
    db.expire_all()
    landing = db.query(LandingPage).filter_by(id=landing.id).one()
    assert landing.review_status == ReviewStatus.approved.value
    assert landing.approved_at is not None

    run_publisher([landing.id], job.id)

    db.expire_all()
    landing = db.query(LandingPage).filter_by(id=landing.id).one()
    assert landing.status == LandingStatus.published.value
    assert landing.review_status == ReviewStatus.published.value
    assert (sites_dir / "public" / landing.slug / "index.html").is_file()
    assert (sites_dir / "public" / landing.slug / "profile.json").is_file()

    campaign = OutreachCampaign(
        id=f"camp_{uuid.uuid4().hex[:10]}",
        name="MVP sandbox",
        channel="whatsapp",
        language="ru",
        status=CampaignStatus.running.value,
    )
    message = OutreachMessage(
        id=f"msg_{uuid.uuid4().hex[:10]}",
        campaign_id=campaign.id,
        lead_id=lead.id,
        channel="whatsapp",
        recipient=sandbox_phone,
        body=f"Здравствуйте! Ваш тестовый лендинг: {landing.preview_url}",
        status=MessageStatus.needs_review.value,
        idempotency_key=f"mvp-e2e-{lead.id}",
    )
    db.add_all([campaign, message])
    db.commit()

    message_approval = TestClient(app).post(
        f"/admin/messages/{message.id}/approve",
        data={"csrf_token": generate_csrf_token()},
        cookies={"admin_auth": "testpass"},
        follow_redirects=False,
    )
    assert message_approval.status_code == 303
    db.expire_all()
    message = db.query(OutreachMessage).filter_by(id=message.id).one()
    assert message.status == MessageStatus.approved.value
    assert message.approved_at is not None

    with monkeypatch.context() as patch:
        patch.setattr(outreach_service, "settings", type("Settings", (), {})())
        patch.setattr(outreach_sender_worker, "settings", type("Settings", (), {})())
        _patch_outreach_settings(outreach_service.settings, sandbox_phone)
        _patch_outreach_settings(outreach_sender_worker.settings, sandbox_phone)
        run_outreach_sender(message.id)

    db.expire_all()
    message = db.query(OutreachMessage).filter_by(id=message.id).one()
    assert message.status == MessageStatus.sent.value
    assert message.provider_message_id

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": f"wa-inbound-{uuid.uuid4().hex[:10]}",
                                    "from": sandbox_phone.lstrip("+"),
                                    "type": "text",
                                    "text": {"body": "Интересно, расскажите подробнее"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    response = TestClient(app).post("/webhooks/whatsapp", json=payload)
    assert response.status_code == 200
    assert response.json()["changed"] == 1

    db.expire_all()
    lead = db.query(Lead).filter_by(id=lead.id).one()
    inbound = db.query(InboundMessage).filter_by(lead_id=lead.id).one()
    assert lead.stage == LeadStage.replied.value
    assert inbound.text_body == "Интересно, расскажите подробнее"

    duplicate = TestClient(app).post("/webhooks/whatsapp", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["changed"] == 0
    assert (
        db.query(InboundMessage)
        .filter_by(provider_message_id=inbound.provider_message_id)
        .count()
        == 1
    )
