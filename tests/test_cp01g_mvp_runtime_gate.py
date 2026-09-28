from __future__ import annotations

import hashlib
import uuid

from fastapi.testclient import TestClient

from app.collector.adapters.csv import CsvCollectorAdapter
from app.config import settings
from app.main import app
from app.models.campaign import OutreachMessage
from app.models.lead import Lead, LeadStatus
from app.models.whatsapp import InboundMessage
from app.security import generate_csrf_token
from app.workers.collector_worker import run_collector
from app.workers.content_generator_worker import run_content_generator
from app.workers.enricher_worker import run_enricher
from app.workers.outreach_generator_worker import run_outreach_generator
from app.workers.outreach_sender_worker import run_outreach_sender


def _record_queues(monkeypatch):
    calls = []

    class RecordingQueue:
        def __init__(self, name, connection=None):
            self.name = name

        def enqueue(self, function, *args, **kwargs):
            calls.append((self.name, function, args, kwargs))

    monkeypatch.setattr("rq.Queue", RecordingQueue)
    monkeypatch.setattr("app.api.routes.Queue", RecordingQueue)
    return calls


def test_csv_fallback_source_id_remains_stable_for_deduplication():
    name = "Stable Furniture"
    city = "Алматы"
    row = {"name": name, "city": city}
    adapter = CsvCollectorAdapter()

    first = adapter._parse_row(row)
    repeated = adapter._parse_row(row)
    expected = hashlib.md5(
        f"{name}:{city}".encode(), usedforsecurity=False
    ).hexdigest()[:12]

    assert first is not None
    assert repeated is not None
    assert first.source_id == expected
    assert repeated.source_id == first.source_id


def test_csv_to_whatsapp_reply_uses_default_worker_runtime(db, tmp_path, monkeypatch):
    """Exercise the documented queue path without substituting SQLite for PostgreSQL."""
    from app.landing import renderer
    from app.publisher import publisher

    suffix = uuid.uuid4().hex[:10]
    duplicate_id = f"cp01g-duplicate-{suffix}"
    first_source_id = f"cp01g-first-{suffix}"
    second_source_id = f"cp01g-second-{suffix}"
    first_phone = f"+7700{uuid.uuid4().int % 10_000_000:07d}"
    second_phone = f"+7701{uuid.uuid4().int % 10_000_000:07d}"
    csv_path = tmp_path / "mvp-leads.csv"
    csv_path.write_text(
        "source_id,name,category,city,address,phone,website,instagram,"
        "rating,reviews_count,source_url,latitude,longitude\n"
        f"{duplicate_id},Already Imported,Мебель на заказ,Алматы,,+77001230001,,"
        ",4.5,20,,43.2,76.9\n"
        f"cp01g-website-{suffix},Has Website,Мебель на заказ,Алматы,,"
        "+77001230002,https://example.test,,4.5,20,,43.2,76.9\n"
        f"cp01g-no-phone-{suffix},No Phone,Мебель на заказ,Алматы,,,,"
        ",4.5,20,,43.2,76.9\n"
        f"{first_source_id},MVP Furniture,Мебель на заказ,Алматы,,{first_phone},,"
        ",4.8,25,,43.2,76.9\n"
        f"{second_source_id},MVP Cabinets,Мебель на заказ,Алматы,,{second_phone},,"
        ",4.7,30,,43.3,76.8\n",
        encoding="utf-8",
    )
    db.add(
        Lead(
            name="Prior CSV import",
            city="Алматы",
            category="Мебель на заказ",
            phone="+77001230001",
            source="csv",
            source_id=duplicate_id,
            status=LeadStatus.collected.value,
        )
    )
    db.commit()

    monkeypatch.setattr(settings, "collector_provider", "csv")
    monkeypatch.setattr(settings, "csv_file_path", str(csv_path))
    monkeypatch.setattr(settings, "csv_page_size", 2)
    monkeypatch.setattr(settings, "verification_enabled", False)
    sites_dir = tmp_path / "sites"
    monkeypatch.setattr(renderer, "SITES_DIR", sites_dir)
    monkeypatch.setattr(publisher, "SITES_DIR", sites_dir)
    queued = _record_queues(monkeypatch)
    client = TestClient(app)

    providers = client.get("/providers")
    assert providers.status_code == 200
    assert providers.json()["current_collector"] == "csv"
    assert "csv" in providers.json()["collector_providers"]

    created_job = client.post(
        "/jobs",
        json={
            "city": "Алматы",
            "category": "Мебель на заказ",
            "limit": 3,
            "provider": "csv",
        },
    )
    assert created_job.status_code == 200
    job_id = created_job.json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "pending"
    assert queued[-1][:3] == (
        "collect",
        "app.workers.collector_worker.run_collector",
        (job_id, "csv"),
    )

    run_collector(job_id, provider="csv")
    db.expire_all()
    collected = (
        db.query(Lead).filter(Lead.search_job_id == job_id).order_by(Lead.id).all()
    )
    assert len(collected) == 2
    lead_ids = [lead.id for lead in collected]
    db.rollback()
    assert queued[-1][:3] == (
        "enrich",
        "app.workers.enricher_worker.run_enricher",
        (lead_ids, job_id),
    )
    assert client.get(f"/jobs/{job_id}").json()["accepted_count"] == 3
    assert client.get(f"/jobs/{job_id}").json()["processed_count"] == 5

    run_enricher(lead_ids, job_id)
    db.expire_all()
    lead = db.query(Lead).filter(Lead.id == lead_ids[0]).one()
    assert lead.status == LeadStatus.enriched.value
    assert lead.slug
    assert lead.whatsapp.startswith("https://wa.me/")
    phone = lead.phone
    db.rollback()
    assert (
        len(
            client.get(
                "/leads",
                params={
                    "city": "Алматы",
                    "category": "Мебель на заказ",
                    "status": "enriched",
                    "provider": "csv",
                    "search_job_id": job_id,
                },
            ).json()
        )
        == 2
    )

    generation_response = client.post(
        f"/leads/{lead_ids[0]}/content-generations",
        json={"provider": "template", "language": "ru", "notes": "Operator review"},
    )
    assert generation_response.status_code == 200
    generation_id = generation_response.json()["id"]
    assert queued[-1][:3] == (
        "generate_content",
        "app.workers.content_generator_worker.run_content_generator",
        (generation_id,),
    )
    run_content_generator(generation_id)
    generation = client.get(f"/content-generations/{generation_id}").json()
    assert generation["status"] == "succeeded"
    assert generation["output_json"]
    landing_id = generation["landing_page_id"]
    assert (
        client.get(
            "/landings",
            params={"lead_id": lead_ids[0], "review_status": "needs_review"},
        ).json()[0]["id"]
        == landing_id
    )
    assert client.get(f"/landings/{landing_id}").status_code == 200

    login = client.post(
        "/admin/login",
        data={"password": settings.admin_password},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert client.get("/admin/leads").status_code == 200
    assert client.get(f"/admin/leads/{lead_ids[0]}").status_code == 200
    assert (
        client.get("/admin/landings", params={"lead_id": lead_ids[0]}).status_code
        == 200
    )
    assert client.get(f"/admin/landings/{landing_id}").status_code == 200
    assert client.get("/admin/settings").status_code == 200

    approved = client.post(
        f"/admin/landings/{landing_id}/approve",
        data={"csrf_token": generate_csrf_token()},
        follow_redirects=False,
    )
    assert approved.status_code == 302
    published = client.post(f"/landings/{landing_id}/publish")
    assert published.status_code == 200
    assert published.json()["review_status"] == "published"
    assert (sites_dir / "public" / published.json()["slug"] / "index.html").is_file()

    campaign_response = client.post(
        "/campaigns",
        json={"name": f"CP-01G {suffix}", "channel": "whatsapp", "language": "kk"},
    )
    assert campaign_response.status_code == 200
    campaign_id = campaign_response.json()["id"]
    added = client.post(
        f"/campaigns/{campaign_id}/add-leads",
        json={"lead_ids": [lead_ids[0], lead_ids[1], lead_ids[0], 99999999]},
    )
    assert added.json() == {"added": 2}
    assert client.post(
        f"/campaigns/{campaign_id}/add-leads",
        json={"lead_ids": lead_ids},
    ).json() == {"added": 0}
    assert client.post(f"/campaigns/{campaign_id}/generate-messages").json() == {
        "status": "queued"
    }
    assert queued[-1][:3] == (
        "outreach_generate",
        "app.workers.outreach_generator_worker.run_outreach_generator",
        (campaign_id,),
    )

    run_outreach_generator(campaign_id)
    db.expire_all()
    messages = (
        db.query(OutreachMessage)
        .filter(OutreachMessage.campaign_id == campaign_id)
        .order_by(OutreachMessage.lead_id)
        .all()
    )
    assert len(messages) == 2
    message = messages[0]
    assert message.status == "needs_review"
    assert message.recipient == phone
    assert "тоқтату" in message.body
    assert published.json()["preview_url"] in message.body
    message_id = message.id
    db.rollback()

    assert client.get(f"/campaigns/{campaign_id}").status_code == 200
    assert client.get("/campaigns", params={"status": "ready"}).status_code == 200
    assert (
        len(
            client.get(
                f"/campaigns/{campaign_id}/messages", params={"status": "needs_review"}
            ).json()
        )
        == 2
    )
    assert (
        client.get(
            "/outreach-messages",
            params={"campaign_id": campaign_id, "status": "needs_review"},
        ).status_code
        == 200
    )
    assert client.get(f"/outreach-messages/{message_id}").status_code == 200
    assert client.get("/admin/messages").status_code == 200

    message_approval = client.post(
        f"/admin/messages/{message_id}/approve",
        data={"csrf_token": generate_csrf_token()},
        follow_redirects=False,
    )
    assert message_approval.status_code == 303
    monkeypatch.setattr(settings, "outreach_enabled", True)
    monkeypatch.setattr(settings, "outreach_mode", "sandbox")
    monkeypatch.setattr(settings, "outreach_sandbox_allowlist", phone)
    monkeypatch.setattr(settings, "outreach_provider", "mock")
    monkeypatch.setattr(settings, "outreach_max_per_hour", 1000)
    monkeypatch.setattr(settings, "outreach_quiet_hours_start", "00:00")
    monkeypatch.setattr(settings, "outreach_quiet_hours_end", "00:00")
    monkeypatch.setattr(settings, "outreach_timezone", "Asia/Almaty")
    queued_send = client.post(f"/outreach-messages/{message_id}/send")
    assert queued_send.status_code == 200
    assert queued_send.json()["status"] == "queued"
    assert queued[-1][:3] == (
        "outreach_send",
        "app.workers.outreach_sender_worker.run_outreach_sender",
        (message_id,),
    )
    run_outreach_sender(message_id)
    db.expire_all()
    sent = db.query(OutreachMessage).filter_by(id=message_id).one()
    assert sent.status == "sent"
    provider_message_id = sent.provider_message_id
    db.rollback()

    verification = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.whatsapp_webhook_verify_token,
            "hub.challenge": "cp01g-challenge",
        },
    )
    assert verification.status_code == 200
    assert verification.text == "cp01g-challenge"
    assert (
        client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "cp01g-challenge",
            },
        ).status_code
        == 403
    )

    delivery = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": provider_message_id,
                                    "status": "delivered",
                                    "timestamp": "cp01g-delivery",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    assert client.post("/webhooks/whatsapp", json=delivery).json()["changed"] == 1
    assert client.post("/webhooks/whatsapp", json=delivery).json()["changed"] == 0

    inbound_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": f"wamid.cp01g.{suffix}",
                                    "from": phone.lstrip("+"),
                                    "type": "text",
                                    "text": {"body": "Қызық, толық айтып беріңізші"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    inbound_response = client.post("/webhooks/whatsapp", json=inbound_payload)
    assert inbound_response.status_code == 200
    assert inbound_response.json()["changed"] == 1
    assert (
        client.post("/webhooks/whatsapp", json=inbound_payload).json()["changed"] == 0
    )
    inbound = client.get("/inbound-messages", params={"lead_id": lead_ids[0]}).json()[0]
    assert inbound["text_body"] == "Қызық, толық айтып беріңізші"
    handled = client.post(f"/inbound-messages/{inbound['id']}/mark-handled")
    assert handled.status_code == 200
    assert handled.json()["status"] == "handled"
    assert client.get("/admin/inbox").status_code == 200
    db.expire_all()
    replied_lead = db.query(Lead).filter_by(id=lead_ids[0]).one()
    assert replied_lead.stage == "replied"
    assert db.query(InboundMessage).filter_by(id=inbound["id"]).count() == 1


def test_message_templates_and_safety_policies_cover_mvp_choices(db, monkeypatch):
    from app.outreach.message_generator import MessageContext, generate_messages
    from app.outreach.service import can_send_message

    russian = generate_messages(
        MessageContext(
            company_name="Алматы Мебель",
            city="Алматы",
            category="Мебель на заказ",
            preview_url="https://example.test/landing",
            language="ru",
        )
    )
    kazakh = generate_messages(
        MessageContext(company_name="Алматы Мебель", city="", language="kk")
    )
    assert "Алматы" in russian.whatsapp_short
    assert "https://example.test/landing" in russian.first_contact
    assert "стоп" in russian.first_contact
    assert "тоқтату" in kazakh.whatsapp_short
    assert "Сіздің компания" not in kazakh.whatsapp_short

    lead = Lead(
        name="Policy check",
        city="Алматы",
        phone="+77001234567",
        status=LeadStatus.enriched.value,
    )
    db.add(lead)
    db.flush()
    from app.models.campaign import CampaignStatus, OutreachCampaign

    campaign = OutreachCampaign(
        id=f"policy-{uuid.uuid4().hex[:8]}",
        name="Policy check",
        channel="whatsapp",
        language="ru",
        status=CampaignStatus.running.value,
    )
    db.add(campaign)
    db.flush()
    message = OutreachMessage(
        id=f"policy-msg-{uuid.uuid4().hex[:8]}",
        campaign_id=campaign.id,
        lead_id=lead.id,
        channel="whatsapp",
        recipient=lead.phone,
        body="Review before sending",
        status="queued",
    )
    db.add(message)
    db.commit()

    monkeypatch.setattr(settings, "outreach_enabled", True)
    monkeypatch.setattr(settings, "outreach_mode", "sandbox")
    monkeypatch.setattr(settings, "outreach_sandbox_allowlist", "+77001234567")
    monkeypatch.setattr(settings, "outreach_quiet_hours_start", "00:00")
    monkeypatch.setattr(settings, "outreach_quiet_hours_end", "00:00")
    monkeypatch.setattr(settings, "outreach_max_per_hour", 1000)
    assert can_send_message(message)[0] is True

    lead.do_not_contact = True
    lead.do_not_contact_reason = "Requested no contact"
    db.commit()
    allowed, reason = can_send_message(message)
    assert allowed is False
    assert "do_not_contact" in reason


def test_admin_reject_and_whatsapp_template_consent_endpoints(db, monkeypatch):
    suffix = uuid.uuid4().hex[:10]
    phone = f"+7702{uuid.uuid4().int % 10_000_000:07d}"
    lead = Lead(
        name=f"Review Lead {suffix}",
        city="Алматы",
        phone=phone,
        status=LeadStatus.enriched.value,
    )
    db.add(lead)
    db.commit()

    from app.models.landing_page import LandingPage, LandingStatus, ReviewStatus

    landing = LandingPage(
        id=f"review-{suffix}",
        lead_id=lead.id,
        slug=f"review-{suffix}",
        title="Review landing",
        profile_json="{}",
        status=LandingStatus.draft.value,
        review_status=ReviewStatus.needs_review.value,
    )
    db.add(landing)
    db.commit()

    client = TestClient(app)
    assert client.get("/admin/login").status_code == 200
    assert client.post("/admin/login", data={"password": "wrong"}).status_code == 401
    client.cookies.set("admin_auth", settings.admin_password)
    rejected = client.post(
        f"/admin/landings/{landing.id}/reject",
        data={
            "reason": "Incorrect contact details",
            "csrf_token": generate_csrf_token(),
        },
        follow_redirects=False,
    )
    assert rejected.status_code == 302
    db.expire_all()
    assert (
        db.query(LandingPage).filter_by(id=landing.id).one().review_status == "rejected"
    )

    template = client.post(
        "/whatsapp/templates",
        json={
            "name": f"mvp_{suffix}",
            "language_code": "ru",
            "category": "MARKETING",
            "body_template": "Hello {{1}}",
        },
    )
    assert template.status_code == 200
    assert (
        client.get("/whatsapp/templates", params={"status": "draft"}).status_code == 200
    )

    invalid_consent = client.put(
        f"/leads/{lead.id}/consent", json={"consent_status": "not-a-status"}
    )
    assert invalid_consent.status_code == 400
    withdrawn = client.put(
        f"/leads/{lead.id}/consent",
        json={
            "consent_status": "withdrawn",
            "contact_basis": "operator review",
            "consent_source": "customer request",
            "consent_notes": "Do not contact again",
        },
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["do_not_contact"] is True
    assert (
        client.get(
            "/inbound-messages", params={"lead_id": lead.id, "status": "new"}
        ).status_code
        == 200
    )
    monkeypatch.setattr(settings, "whatsapp_app_secret", "test-signing-secret")
    monkeypatch.setattr(settings, "whatsapp_allow_mock_webhooks", False)
    invalid_signature = client.post("/webhooks/whatsapp", json={"entry": []})
    assert invalid_signature.status_code == 200
    assert invalid_signature.json()["reason"] == "invalid_signature"
