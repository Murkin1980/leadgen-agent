from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api import admin_recovery
from app.main import app
from app.models.campaign import CampaignStatus, MessageStatus, OutreachCampaign, OutreachMessage
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.lead import Lead, LeadStatus
from app.models.stage import LeadStage
from app.security import generate_csrf_token


class FakeQueue:
    calls: list[tuple[str, tuple, dict]] = []

    def __init__(self, name: str, connection=None):
        self.name = name

    def enqueue(self, *args, **kwargs):
        self.calls.append((self.name, args, kwargs))
        return object()


def _client() -> TestClient:
    client = TestClient(app)
    client.cookies.set("admin_auth", "testpass")
    return client


def _lead(db, *, dnc: bool = False) -> Lead:
    lead = Lead(
        name="Recovery Test",
        city="Алматы",
        phone="+77000000001",
        whatsapp="+77000000001",
        status=LeadStatus.enriched.value,
        stage=LeadStage.ready_for_outreach.value,
        do_not_contact=dnc,
    )
    db.add(lead)
    db.flush()
    return lead


def test_recovery_page_requires_auth():
    response = TestClient(app).get("/admin/recovery")
    assert response.status_code == 401


def test_failed_generation_can_be_requeued(db, monkeypatch):
    FakeQueue.calls.clear()
    monkeypatch.setattr(admin_recovery, "Queue", FakeQueue)
    lead = _lead(db)
    generation = ContentGeneration(
        id=f"gen_{uuid.uuid4().hex[:10]}",
        lead_id=lead.id,
        provider="template",
        prompt_version="v1",
        status=ContentGenerationStatus.failed.value,
        error_message="temporary generator failure",
    )
    db.add(generation)
    db.commit()

    response = _client().post(
        f"/admin/recovery/generations/{generation.id}/retry",
        data={"csrf_token": generate_csrf_token()},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.refresh(generation)
    assert generation.status == ContentGenerationStatus.queued.value
    assert generation.error_message is None
    assert FakeQueue.calls[0][0] == "generate_content"


def test_succeeded_generation_is_not_retryable(db, monkeypatch):
    monkeypatch.setattr(admin_recovery, "Queue", FakeQueue)
    lead = _lead(db)
    generation = ContentGeneration(
        id=f"gen_{uuid.uuid4().hex[:10]}",
        lead_id=lead.id,
        provider="template",
        prompt_version="v1",
        status=ContentGenerationStatus.succeeded.value,
    )
    db.add(generation)
    db.commit()

    response = _client().post(
        f"/admin/recovery/generations/{generation.id}/retry",
        data={"csrf_token": generate_csrf_token()},
    )
    assert response.status_code == 409


def test_retryable_failed_message_can_be_requeued(db, monkeypatch):
    FakeQueue.calls.clear()
    monkeypatch.setattr(admin_recovery, "Queue", FakeQueue)
    lead = _lead(db)
    campaign = OutreachCampaign(
        id=f"camp_{uuid.uuid4().hex[:10]}",
        name="Recovery",
        channel="whatsapp",
        status=CampaignStatus.running.value,
    )
    message = OutreachMessage(
        id=f"msg_{uuid.uuid4().hex[:10]}",
        campaign_id=campaign.id,
        lead_id=lead.id,
        channel="whatsapp",
        recipient=lead.phone,
        body="Тест",
        status=MessageStatus.failed.value,
        retryable=True,
        error_message="temporary provider error",
    )
    db.add_all([campaign, message])
    db.commit()

    response = _client().post(
        f"/admin/recovery/messages/{message.id}/retry",
        data={"csrf_token": generate_csrf_token()},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.refresh(message)
    assert message.status == MessageStatus.queued.value
    assert message.error_message is None
    assert FakeQueue.calls[0][0] == "outreach_send"


def test_blocked_or_dnc_message_cannot_be_requeued(db, monkeypatch):
    FakeQueue.calls.clear()
    monkeypatch.setattr(admin_recovery, "Queue", FakeQueue)
    lead = _lead(db, dnc=True)
    campaign = OutreachCampaign(
        id=f"camp_{uuid.uuid4().hex[:10]}",
        name="Blocked",
        channel="whatsapp",
        status=CampaignStatus.running.value,
    )
    message = OutreachMessage(
        id=f"msg_{uuid.uuid4().hex[:10]}",
        campaign_id=campaign.id,
        lead_id=lead.id,
        channel="whatsapp",
        recipient=lead.phone,
        body="Не отправлять",
        status=MessageStatus.failed.value,
        retryable=True,
    )
    db.add_all([campaign, message])
    db.commit()

    response = _client().post(
        f"/admin/recovery/messages/{message.id}/retry",
        data={"csrf_token": generate_csrf_token()},
    )
    assert response.status_code == 409
    assert FakeQueue.calls == []


def test_retry_requires_valid_csrf(db, monkeypatch):
    monkeypatch.setattr(admin_recovery, "Queue", FakeQueue)
    lead = _lead(db)
    generation = ContentGeneration(
        id=f"gen_{uuid.uuid4().hex[:10]}",
        lead_id=lead.id,
        provider="template",
        prompt_version="v1",
        status=ContentGenerationStatus.failed.value,
    )
    db.add(generation)
    db.commit()

    response = _client().post(
        f"/admin/recovery/generations/{generation.id}/retry",
        data={"csrf_token": "invalid"},
    )
    assert response.status_code == 403
