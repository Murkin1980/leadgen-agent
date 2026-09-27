from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.campaign import MessageStatus, OutreachCampaign, OutreachMessage
from app.models.lead import Lead
from app.security import generate_csrf_token


AUTH = {"admin_auth": "testpass"}


def _message(db, status: str = MessageStatus.needs_review.value) -> OutreachMessage:
    lead = Lead(name="Approval Test", city="Алматы", phone="+77000000001")
    db.add(lead)
    db.flush()
    campaign = OutreachCampaign(
        id=f"camp-approval-{lead.id}",
        name="Approval test",
        channel="whatsapp",
        status="draft",
    )
    db.add(campaign)
    db.flush()
    message = OutreachMessage(
        id=f"msg-approval-{lead.id}",
        campaign_id=campaign.id,
        lead_id=lead.id,
        channel="whatsapp",
        recipient="+77000000001",
        body="Тестовое сообщение",
        status=status,
    )
    db.add(message)
    db.commit()
    return message


def test_messages_page_uses_post_form(db):
    message = _message(db)
    response = TestClient(app).get("/admin/messages", cookies=AUTH)
    assert response.status_code == 200
    assert f'action="/admin/messages/{message.id}/approve"' in response.text
    assert 'method="post"' in response.text
    assert f'href="/admin/messages/{message.id}/approve' not in response.text


def test_get_approval_is_rejected(db):
    message = _message(db)
    response = TestClient(app).get(
        f"/admin/messages/{message.id}/approve",
        cookies=AUTH,
    )
    assert response.status_code == 405
    db.refresh(message)
    assert message.status == MessageStatus.needs_review.value


def test_post_approval_requires_csrf(db):
    message = _message(db)
    response = TestClient(app).post(
        f"/admin/messages/{message.id}/approve",
        data={"csrf_token": "invalid"},
        cookies=AUTH,
    )
    assert response.status_code == 403
    db.refresh(message)
    assert message.status == MessageStatus.needs_review.value


def test_post_approval_changes_only_needs_review(db):
    message = _message(db)
    response = TestClient(app).post(
        f"/admin/messages/{message.id}/approve",
        data={"csrf_token": generate_csrf_token()},
        cookies=AUTH,
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.refresh(message)
    assert message.status == MessageStatus.approved.value
    assert message.approved_at is not None


def test_already_sent_message_cannot_be_approved(db):
    message = _message(db, MessageStatus.sent.value)
    response = TestClient(app).post(
        f"/admin/messages/{message.id}/approve",
        data={"csrf_token": generate_csrf_token()},
        cookies=AUTH,
    )
    assert response.status_code == 409
    db.refresh(message)
    assert message.status == MessageStatus.sent.value
