"""Targeted regression tests for retries and duplicate protection.

These tests intentionally use the existing database, workers and state guards.
No generalized idempotency subsystem is introduced.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.models.campaign import CampaignStatus, MessageStatus, OutreachCampaign, OutreachMessage
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import LandingPage, LandingStatus, ReviewStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import JobStatus, SearchJob
from app.models.stage import LeadStage
from app.outreach.provider import SendResult
from app.workers.content_generator_worker import run_content_generator
from app.workers.outreach_sender_worker import run_outreach_sender
from app.workers.publisher_worker import run_publisher


SANDBOX_PHONE = "+77000000001"


def _allow_sandbox(settings_obj) -> None:
    settings_obj.outreach_enabled = True
    settings_obj.outreach_mode = "sandbox"
    settings_obj.sandbox_allowlist = {SANDBOX_PHONE}
    settings_obj.outreach_timezone = "Asia/Almaty"
    settings_obj.outreach_quiet_hours_start = "00:00"
    settings_obj.outreach_quiet_hours_end = "00:00"
    settings_obj.outreach_max_per_hour = 1000
    settings_obj.outreach_provider = "mock"
    settings_obj.outreach_send_max_retries = 2
    settings_obj.outreach_send_retry_base_seconds = 1


def _create_publishable_landing(db, slug: str):
    lead = Lead(
        name="ТОО Тест Мебель",
        city="Алматы",
        category="Мебель на заказ",
        phone=SANDBOX_PHONE,
        whatsapp=SANDBOX_PHONE,
        slug=slug,
        status=LeadStatus.generated.value,
        stage=LeadStage.landing_generated.value,
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
        id=f"gen_{uuid.uuid4().hex[:10]}",
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
    landing = db.query(LandingPage).filter_by(id=generation.landing_page_id).one()
    landing.review_status = ReviewStatus.approved.value
    landing.status = LandingStatus.approved.value
    landing.approved_by = "test"
    landing.approved_at = datetime.now(timezone.utc)
    db.commit()
    return lead.id, job.id, landing.id


def test_sender_second_run_does_not_call_provider_twice(db, monkeypatch):
    """A completed message is a terminal no-op on repeated worker execution."""
    from app.outreach import service as outreach_service
    from app.workers import outreach_sender_worker

    lead = Lead(
        name="Sandbox duplicate send",
        city="Алматы",
        phone=SANDBOX_PHONE,
        whatsapp=SANDBOX_PHONE,
        status=LeadStatus.published.value,
        stage=LeadStage.ready_for_outreach.value,
    )
    campaign = OutreachCampaign(
        id=f"camp_{uuid.uuid4().hex[:10]}",
        name="Duplicate send test",
        channel="whatsapp",
        language="ru",
        status=CampaignStatus.running.value,
    )
    db.add_all([lead, campaign])
    db.flush()
    message = OutreachMessage(
        id=f"msg_{uuid.uuid4().hex[:10]}",
        campaign_id=campaign.id,
        lead_id=lead.id,
        channel="whatsapp",
        recipient=SANDBOX_PHONE,
        body="Тест повторной отправки",
        status=MessageStatus.queued.value,
        approved_by="test",
        approved_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.commit()

    calls = {"count": 0}

    class CountingProvider:
        def send(self, **kwargs):
            calls["count"] += 1
            return SendResult(
                success=True,
                provider_message_id="mock-fixed-provider-id",
                provider_status="sent",
                raw_response={"mock": True},
            )

    service_settings = type("Settings", (), {})()
    worker_settings = type("Settings", (), {})()
    _allow_sandbox(service_settings)
    _allow_sandbox(worker_settings)
    monkeypatch.setattr(outreach_service, "settings", service_settings)
    monkeypatch.setattr(outreach_sender_worker, "settings", worker_settings)
    monkeypatch.setattr(outreach_sender_worker, "create_outreach_provider", lambda: CountingProvider())

    run_outreach_sender(message.id)
    run_outreach_sender(message.id)

    db.expire_all()
    message = db.query(OutreachMessage).filter_by(id=message.id).one()
    assert message.status == MessageStatus.sent.value
    assert message.provider_message_id == "mock-fixed-provider-id"
    assert calls["count"] == 1


def test_republishing_approved_landing_is_safe(db, tmp_path, monkeypatch):
    """Publishing the same landing twice replaces output atomically without duplication."""
    from app.landing import renderer
    from app.publisher import publisher

    sites_dir = tmp_path / "sites"
    monkeypatch.setattr(renderer, "SITES_DIR", sites_dir)
    monkeypatch.setattr(publisher, "SITES_DIR", sites_dir)

    lead_id, job_id, landing_id = _create_publishable_landing(
        db, f"repeat-publish-{uuid.uuid4().hex[:8]}"
    )

    run_publisher([landing_id], job_id)
    first_index = (sites_dir / "public").glob("*/index.html")
    first_files = list(first_index)
    assert len(first_files) == 1
    first_html = first_files[0].read_text(encoding="utf-8")

    # The worker requires approval; simulate an explicit admin re-approval.
    landing = db.query(LandingPage).filter_by(id=landing_id).one()
    landing.review_status = ReviewStatus.approved.value
    db.commit()
    run_publisher([landing_id], job_id)

    db.expire_all()
    landing = db.query(LandingPage).filter_by(id=landing_id).one()
    lead = db.query(Lead).filter_by(id=lead_id).one()
    output_dir = sites_dir / "public" / landing.slug
    assert landing.status == LandingStatus.published.value
    assert lead.status == LeadStatus.published.value
    assert (output_dir / "index.html").read_text(encoding="utf-8") == first_html
    assert len(list((sites_dir / "public").glob("*/index.html"))) == 1


def test_publication_failure_does_not_mark_lead_published(db, tmp_path, monkeypatch):
    """Invalid landing data fails locally and leaves the lead out of published state."""
    from app.landing import renderer
    from app.publisher import publisher

    sites_dir = tmp_path / "sites"
    monkeypatch.setattr(renderer, "SITES_DIR", sites_dir)
    monkeypatch.setattr(publisher, "SITES_DIR", sites_dir)

    lead = Lead(
        name="Broken landing",
        city="Алматы",
        slug=f"broken-{uuid.uuid4().hex[:8]}",
        status=LeadStatus.generated.value,
        stage=LeadStage.landing_generated.value,
    )
    job = SearchJob(
        city="Алматы",
        category="Мебель",
        provider="mock",
        status=JobStatus.pending.value,
        limit=1,
    )
    db.add_all([lead, job])
    db.flush()
    landing = LandingPage(
        id=f"lp_{uuid.uuid4().hex[:10]}",
        lead_id=lead.id,
        slug=lead.slug,
        title="Broken",
        profile_json="{not-json",
        status=LandingStatus.approved.value,
        review_status=ReviewStatus.approved.value,
    )
    db.add(landing)
    db.commit()

    run_publisher([landing.id], job.id)

    db.expire_all()
    landing = db.query(LandingPage).filter_by(id=landing.id).one()
    lead = db.query(Lead).filter_by(id=lead.id).one()
    assert landing.status == LandingStatus.failed.value
    assert lead.status != LeadStatus.published.value
    assert not (sites_dir / "public" / landing.slug).exists()


def test_generation_failure_is_visible_and_does_not_create_landing(db):
    """An invalid provider produces a failed generation with a readable error."""
    lead = Lead(
        name="Generation failure",
        city="Алматы",
        slug=f"generation-failure-{uuid.uuid4().hex[:8]}",
        status=LeadStatus.enriched.value,
        stage=LeadStage.new.value,
    )
    db.add(lead)
    db.flush()
    generation = ContentGeneration(
        id=f"gen_{uuid.uuid4().hex[:10]}",
        lead_id=lead.id,
        provider="provider-that-does-not-exist",
        prompt_version="v1",
        status=ContentGenerationStatus.queued.value,
        language="ru",
    )
    db.add(generation)
    db.commit()

    run_content_generator(generation.id)

    db.expire_all()
    generation = db.query(ContentGeneration).filter_by(id=generation.id).one()
    assert generation.status == ContentGenerationStatus.failed.value
    assert generation.error_message
    assert generation.landing_page_id is None
    assert db.query(LandingPage).filter_by(generation_id=generation.id).count() == 0


def test_terminal_blocked_message_is_not_resendable(db, monkeypatch):
    """A policy-blocked message remains terminal when the worker is invoked again."""
    from app.outreach import service as outreach_service
    from app.workers import outreach_sender_worker

    lead = Lead(
        name="DNC lead",
        city="Алматы",
        phone=SANDBOX_PHONE,
        whatsapp=SANDBOX_PHONE,
        do_not_contact=True,
        do_not_contact_reason="Test block",
        status=LeadStatus.published.value,
        stage=LeadStage.do_not_contact.value,
    )
    campaign = OutreachCampaign(
        id=f"camp_{uuid.uuid4().hex[:10]}",
        name="Blocked test",
        channel="whatsapp",
        language="ru",
        status=CampaignStatus.running.value,
    )
    db.add_all([lead, campaign])
    db.flush()
    message = OutreachMessage(
        id=f"msg_{uuid.uuid4().hex[:10]}",
        campaign_id=campaign.id,
        lead_id=lead.id,
        channel="whatsapp",
        recipient=SANDBOX_PHONE,
        body="Не должно быть отправлено",
        status=MessageStatus.queued.value,
    )
    db.add(message)
    db.commit()

    service_settings = type("Settings", (), {})()
    worker_settings = type("Settings", (), {})()
    _allow_sandbox(service_settings)
    _allow_sandbox(worker_settings)
    monkeypatch.setattr(outreach_service, "settings", service_settings)
    monkeypatch.setattr(outreach_sender_worker, "settings", worker_settings)

    run_outreach_sender(message.id)
    run_outreach_sender(message.id)

    db.expire_all()
    message = db.query(OutreachMessage).filter_by(id=message.id).one()
    assert message.status == MessageStatus.blocked.value
    assert message.retryable is False
    assert "do_not_contact" in (message.error_message or "")
    assert message.provider_message_id is None
