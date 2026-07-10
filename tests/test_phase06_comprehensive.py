"""Phase 06 comprehensive tests — WhatsApp production operations.

Covers all 20 categories from the spec, adapted to match the actual
remote codebase interfaces.
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.database import SessionLocal
from app.models.campaign import (
    MessageStatus,
    OutreachCampaign,
    OutreachMessage,
)
from app.models.event import OutreachEvent
from app.models.lead import ConsentStatus, Lead, LeadStatus
from app.models.whatsapp import InboundMessage, WhatsAppTemplate, WhatsAppTemplateStatus
from app.outreach.phone import PhoneNumberError, PhoneNumberService
from app.outreach.service import can_send_message, cancel_pending_follow_ups
from app.outreach.whatsapp_provider import WhatsAppCloudProvider
from app.outreach.webhook_handler import process_webhook_event
from app.security import generate_csrf_token, validate_csrf_token, verify_webhook_signature


# Valid KZ phone numbers (no repeated digit suffixes)
PH1 = "+77071234567"
PH2 = "+77072345678"
PH3 = "+77073456789"
PH4 = "+77074567890"
PH5 = "+77075678901"
PH6 = "+77076789012"
PH7 = "+77012345678"


# ── 1. Phone normalization ────────────────────────────────────────

class TestPhoneNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("8 707 123 45 67", "+77071234567"),
            ("+7 (707) 123-45-67", "+77071234567"),
            ("77071234567", "+77071234567"),
            ("7071234567", "+77071234567"),
            ("  +7 701 555 1234  ", "+77015551234"),
        ],
    )
    def test_kz_normalize(self, raw, expected):
        assert PhoneNumberService.normalize(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [None, "123", "abc", "not-a-phone"],
    )
    def test_invalid_raises(self, raw):
        with pytest.raises(PhoneNumberError):
            PhoneNumberService.normalize(raw)

    def test_rejected_service_number(self):
        with pytest.raises(PhoneNumberError, match="Service or obviously invalid"):
            PhoneNumberService.normalize("+77008888888")

    def test_provider_recipient_strips_plus(self):
        assert PhoneNumberService.provider_recipient("+77071234567") == "77071234567"


# ── 2. Masked logging ────────────────────────────────────────────

class TestMaskedLogging:
    def test_mask_hides_middle_digits(self):
        masked = PhoneNumberService.mask("+77071234567")
        assert "******" in masked
        assert "4567" in masked

    def test_mask_short_phone_returns_invalid(self):
        assert PhoneNumberService.mask("123") == "<invalid-phone>"

    def test_mask_none(self):
        assert PhoneNumberService.mask(None) == "<invalid-phone>"


# ── 3. Sandbox allowlist (worker-level check) ────────────────────

class TestSandboxAllowlist:
    def test_allowed_in_sandbox(self):
        lead = MagicMock()
        lead.do_not_contact = False
        lead.consent_status = "consented"
        with patch("app.workers.outreach_sender_worker.settings") as mock:
            mock.outreach_mode = "sandbox"
            mock.outreach_enabled = True
            mock.sandbox_allowlist = {PH1}
            from app.workers.outreach_sender_worker import _production_policy_allows
            ok, reason = _production_policy_allows(lead, PH1)
            assert ok is True

    def test_blocked_in_sandbox(self):
        lead = MagicMock()
        lead.do_not_contact = False
        lead.consent_status = "consented"
        with patch("app.workers.outreach_sender_worker.settings") as mock:
            mock.outreach_mode = "sandbox"
            mock.outreach_enabled = True
            mock.sandbox_allowlist = {PH1}
            from app.workers.outreach_sender_worker import _production_policy_allows
            ok, reason = _production_policy_allows(lead, PH2)
            assert ok is False
            assert "sandbox" in reason.lower()

    def test_disabled_mode_blocks_all(self):
        lead = MagicMock()
        with patch("app.workers.outreach_sender_worker.settings") as mock:
            mock.outreach_mode = "disabled"
            mock.outreach_enabled = False
            from app.workers.outreach_sender_worker import _production_policy_allows
            ok, reason = _production_policy_allows(lead, PH1)
            assert ok is False


# ── 4. DNC blocking ──────────────────────────────────────────────

class TestDNCBlocking:
    def test_dnc_lead_blocked(self, db):
        with patch("app.workers.outreach_sender_worker.settings") as mock:
            mock.outreach_mode = "production"
            mock.outreach_enabled = True
            mock.sandbox_allowlist = set()
            from app.workers.outreach_sender_worker import _production_policy_allows
            lead = Lead(
                name="DNC Lead", city="Almaty", phone=PH3,
                status=LeadStatus.enriched.value, stage="ready_for_outreach",
                do_not_contact=True, do_not_contact_reason="Opted out",
            )
            db.add(lead)
            db.commit()
            ok, reason = _production_policy_allows(lead, PH3)
            assert ok is False
            assert "do-not-contact" in reason.lower()


# ── 5. Consent blocking ──────────────────────────────────────────

class TestConsentBlocking:
    def test_unknown_consent_blocks_in_production(self):
        lead = MagicMock()
        lead.do_not_contact = False
        lead.consent_status = "unknown"
        with patch("app.workers.outreach_sender_worker.settings") as mock:
            mock.outreach_mode = "production"
            mock.outreach_enabled = True
            mock.sandbox_allowlist = set()
            from app.workers.outreach_sender_worker import _production_policy_allows
            ok, reason = _production_policy_allows(lead, PH4)
            assert ok is False
            assert "contact basis" in reason.lower()

    def test_consented_lead_passes_in_production(self):
        lead = MagicMock()
        lead.do_not_contact = False
        lead.consent_status = "consented"
        with patch("app.workers.outreach_sender_worker.settings") as mock:
            mock.outreach_mode = "production"
            mock.outreach_enabled = True
            mock.sandbox_allowlist = set()
            from app.workers.outreach_sender_worker import _production_policy_allows
            ok, reason = _production_policy_allows(lead, PH4)
            assert ok is True


# ── 6. Manual approval requirement ───────────────────────────────

class TestManualApproval:
    def test_draft_cannot_send(self, db):
        with patch("app.outreach.service.settings") as mock:
            mock.outreach_enabled = True
            mock.outreach_timezone = "Asia/Almaty"
            mock.outreach_quiet_hours_start = "00:00"
            mock.outreach_quiet_hours_end = "00:00"
            mock.outreach_max_per_hour = 1000
            lead = Lead(
                name="Draft Lead", city="Almaty", phone=PH5,
                status=LeadStatus.enriched.value, stage="ready_for_outreach",
            )
            db.add(lead)
            db.flush()
            campaign = OutreachCampaign(
                id=str(uuid.uuid4())[:12], name="Test", channel="whatsapp",
                language="ru", status="draft",
            )
            db.add(campaign)
            db.flush()
            msg = OutreachMessage(
                id=str(uuid.uuid4())[:12], campaign_id=campaign.id,
                lead_id=lead.id, channel="whatsapp",
                recipient=PH5, body="Hi",
                status=MessageStatus.draft.value,
            )
            db.add(msg)
            db.commit()
            ok, reason = can_send_message(msg)
            assert ok is False
            assert "approved" in reason


# ── 7. Service window check ──────────────────────────────────────

class TestServiceWindowLogic:
    def test_sender_worker_service_window_active(self):
        from app.workers.outreach_sender_worker import _service_window_active
        lead = MagicMock()
        lead.service_window_expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
        assert _service_window_active(lead, datetime.now(timezone.utc)) is True

    def test_sender_worker_service_window_expired(self):
        from app.workers.outreach_sender_worker import _service_window_active
        lead = MagicMock()
        lead.service_window_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert _service_window_active(lead, datetime.now(timezone.utc)) is False

    def test_sender_worker_service_window_none(self):
        from app.workers.outreach_sender_worker import _service_window_active
        lead = MagicMock()
        lead.service_window_expires_at = None
        assert _service_window_active(lead, datetime.now(timezone.utc)) is False


# ── 8. Webhook verification (GET) ────────────────────────────────

class TestWebhookVerification:
    def test_valid_challenge(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.api.whatsapp_routes.settings") as mock:
            mock.whatsapp_webhook_verify_token = "test_token"
            resp = client.get(
                "/webhooks/whatsapp",
                params={"hub.mode": "subscribe", "hub.verify_token": "test_token", "hub.challenge": "CHALLENGE_123"},
            )
            assert resp.status_code == 200
            assert resp.text == "CHALLENGE_123"

    def test_invalid_token_returns_403(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with patch("app.api.whatsapp_routes.settings") as mock:
            mock.whatsapp_webhook_verify_token = "test_token"
            resp = client.get(
                "/webhooks/whatsapp",
                params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "CHALLENGE_123"},
            )
            assert resp.status_code == 403


# ── 9. Webhook signature validation ──────────────────────────────

class TestWebhookSignature:
    def test_valid_signature_with_prefix(self):
        payload = b'{"test": true}'
        secret = "my_secret"
        raw = hmac.HMAC(secret.encode(), payload, hashlib.sha256).hexdigest()
        sig = f"sha256={raw}"
        assert verify_webhook_signature(payload, sig, secret) is True

    def test_valid_signature_without_prefix(self):
        payload = b'{"test": true}'
        secret = "my_secret"
        raw = hmac.HMAC(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_webhook_signature(payload, raw, secret) is True

    def test_tampered_signature_rejected(self):
        payload = b'{"test": true}'
        secret = "my_secret"
        sig = "sha256=" + hmac.HMAC(secret.encode(), payload, hashlib.sha256).hexdigest()
        tampered = sig[:-1] + ("0" if sig[-1] != "0" else "1")
        assert verify_webhook_signature(payload, tampered, secret) is False

    def test_none_signature(self):
        assert verify_webhook_signature(b'{}', None, "secret") is False

    def test_empty_secret(self):
        assert verify_webhook_signature(b'{}', "sig", "") is False

    def test_whatsapp_routes_signature_check(self):
        from app.api.whatsapp_routes import _verify_signature
        raw = b'{"entry":[]}'
        secret = "test_secret"
        sig = "sha256=" + hmac.HMAC(secret.encode(), raw, hashlib.sha256).hexdigest()
        with patch("app.api.whatsapp_routes.settings") as mock:
            mock.whatsapp_app_secret = secret
            mock.app_env = "development"
            assert _verify_signature(raw, sig) is True

    def test_whatsapp_routes_no_signature_rejected(self):
        from app.api.whatsapp_routes import _verify_signature
        with patch("app.api.whatsapp_routes.settings") as mock:
            mock.whatsapp_app_secret = "some_secret"
            mock.app_env = "production"
            assert _verify_signature(b'{}', None) is False


# ── 10. Webhook idempotency ──────────────────────────────────────

class TestWebhookIdempotency:
    def test_duplicate_event_not_processed_twice(self, db):
        lead = Lead(
            name="Idempotent", city="Almaty", phone=PH4,
            status=LeadStatus.enriched.value, stage="ready_for_outreach",
        )
        db.add(lead)
        db.flush()
        campaign = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="Test", channel="whatsapp",
            language="ru", status="draft",
        )
        db.add(campaign)
        db.flush()
        msg = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign.id,
            lead_id=lead.id, channel="whatsapp",
            recipient=PH4, body="Test",
            status=MessageStatus.sent.value,
            provider_message_id="wamid.dup.test",
        )
        db.add(msg)
        db.commit()

        payload = {
            "entry": [{"changes": [{"value": {
                "statuses": [{"id": "wamid.dup.test", "status": "delivered"}]
            }}]}]
        }
        r1 = process_webhook_event("whatsapp", payload, signature_valid=True)
        assert r1["processed"] is True

        r2 = process_webhook_event("whatsapp", payload, signature_valid=True)
        assert r2["processed"] is False
        assert r2["reason"] == "duplicate_event"


# ── 11. Inbound message creates reply + updates lead (via routes) ─

class TestInboundReply:
    def test_inbound_via_whatsapp_routes(self, db):
        from fastapi.testclient import TestClient
        from app.main import app

        lead = Lead(
            name="Replier", city="Almaty", phone=PH1,
            whatsapp=PH1,
            status=LeadStatus.enriched.value, stage="ready_for_outreach",
        )
        db.add(lead)
        db.commit()

        client = TestClient(app)
        payload = {
            "entry": [{"changes": [{"value": {
                "messages": [{
                    "id": f"wamid.inbound.{uuid.uuid4().hex[:8]}",
                    "from": "77071234567",
                    "type": "text",
                    "text": {"body": "Interested!"},
                }]
            }}]}]
        }
        with patch("app.api.whatsapp_routes._verify_signature", return_value=True):
            resp = client.post("/webhooks/whatsapp", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["changed"] >= 1

        db.refresh(lead)
        assert lead.stage == "replied"
        assert lead.last_inbound_at is not None

    def test_inbound_cancels_pending_follow_ups(self, db):
        from fastapi.testclient import TestClient
        from app.main import app

        lead = Lead(
            name="Cancel FU", city="Almaty", phone=PH2,
            whatsapp=PH2,
            status=LeadStatus.enriched.value, stage="ready_for_outreach",
        )
        db.add(lead)
        db.flush()
        campaign = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="Test", channel="whatsapp",
            language="ru", status="draft",
        )
        db.add(campaign)
        db.flush()
        msg = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign.id,
            lead_id=lead.id, channel="whatsapp",
            recipient=PH2, body="Follow-up",
            status=MessageStatus.approved.value,
        )
        db.add(msg)
        db.commit()

        client = TestClient(app)
        payload = {
            "entry": [{"changes": [{"value": {
                "messages": [{
                    "id": f"wamid.cancel.{uuid.uuid4().hex[:8]}",
                    "from": "77072345678",
                    "type": "text",
                    "text": {"body": "Got it"},
                }]
            }}]}]
        }
        with patch("app.api.whatsapp_routes._verify_signature", return_value=True):
            resp = client.post("/webhooks/whatsapp", json=payload)
        assert resp.status_code == 200

        db.refresh(msg)
        assert msg.status == MessageStatus.cancelled.value


# ── 12. Cancel pending follow-ups service function ───────────────

class TestCancelFollowUps:
    def test_cancels_approved_and_queued(self, db):
        lead = Lead(
            name="FollowUp", city="Almaty", phone=PH5,
            status=LeadStatus.enriched.value, stage="ready_for_outreach",
        )
        db.add(lead)
        db.flush()
        campaign1 = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="Test1", channel="whatsapp",
            language="ru", status="draft",
        )
        campaign2 = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="Test2", channel="email",
            language="ru", status="draft",
        )
        db.add_all([campaign1, campaign2])
        db.flush()
        approved_msg = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign1.id,
            lead_id=lead.id, channel="whatsapp",
            recipient=PH5, body="Approved",
            status=MessageStatus.approved.value,
        )
        queued_msg = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign2.id,
            lead_id=lead.id, channel="email",
            recipient=PH5, body="Queued",
            status=MessageStatus.queued.value,
        )
        db.add_all([approved_msg, queued_msg])
        db.commit()

        count = cancel_pending_follow_ups(db, lead.id)
        assert count == 2
        db.commit()

        db.refresh(approved_msg)
        db.refresh(queued_msg)
        assert approved_msg.status == MessageStatus.cancelled.value
        assert queued_msg.status == MessageStatus.cancelled.value


# ── 13. CSRF token validation ────────────────────────────────────

class TestCSRFPhase06:
    def test_generate_and_validate(self):
        token = generate_csrf_token()
        assert validate_csrf_token(token) is True

    def test_token_consumed(self):
        token = generate_csrf_token()
        assert validate_csrf_token(token) is True
        assert validate_csrf_token(token) is False

    def test_invalid_token(self):
        assert validate_csrf_token("garbage") is False


# ── 14. Secrets absent from logs ─────────────────────────────────

class TestSecretsNotInLogs:
    def test_mask_phone_not_full_number(self):
        masked = PhoneNumberService.mask(PH6)
        assert "******" in masked

    def test_whatsapp_log_masks_recipient(self, caplog):
        with caplog.at_level(logging.WARNING):
            with patch("app.outreach.whatsapp_provider.settings") as mock:
                mock.whatsapp_cloud_api_token = "REAL_SECRET_TOKEN"
                mock.whatsapp_cloud_phone_number_id = "12345"
                mock.whatsapp_graph_api_version = "v23.0"
                mock.whatsapp_request_timeout_seconds = 30
                mock.whatsapp_app_secret = ""
                provider = WhatsAppCloudProvider()
                provider.send(recipient=PH6, body="test")
        for record in caplog.records:
            assert "REAL_SECRET_TOKEN" not in record.message


# ── 15. Migration model smoke tests ──────────────────────────────

class TestMigration006Models:
    def test_whatsapp_template_crud(self, db):
        t = WhatsAppTemplate(
            id="tpl_test1", name="test_template", language_code="ru",
            body_template="Hello {{name}}", status=WhatsAppTemplateStatus.draft.value,
        )
        db.add(t)
        db.commit()
        assert t.id == "tpl_test1"
        db.delete(t)
        db.commit()

    def test_inbound_message_model(self, db):
        im = InboundMessage(
            id="inb_test1", provider="whatsapp",
            provider_message_id=f"wamid.unique.{uuid.uuid4().hex[:8]}",
            from_phone=PH7, message_type="text",
            text_body="Hello",
        )
        db.add(im)
        db.commit()
        assert im.status == "new"
        db.delete(im)
        db.commit()

    def test_lead_consent_fields(self, db):
        lead = Lead(
            name="Consent Test", city="Almaty", phone=PH7,
            status=LeadStatus.enriched.value,
            consent_status=ConsentStatus.consented.value,
            consent_source="manual_review",
            contact_basis="business_interest",
        )
        db.add(lead)
        db.commit()
        fresh = SessionLocal()
        l = fresh.query(Lead).filter(Lead.phone == PH7).first()
        assert l.consent_status == "consented"
        assert l.contact_basis == "business_interest"
        fresh.close()
        db.delete(lead)
        db.commit()

    def test_outreach_message_retry_fields(self, db):
        lead = Lead(
            name="Retry Test", city="Almaty", phone=PH6,
            status=LeadStatus.enriched.value,
        )
        db.add(lead)
        db.flush()
        campaign = OutreachCampaign(
            id=str(uuid.uuid4())[:12], name="Retry", channel="whatsapp",
            language="ru", status="draft",
        )
        db.add(campaign)
        db.flush()
        msg = OutreachMessage(
            id=str(uuid.uuid4())[:12], campaign_id=campaign.id,
            lead_id=lead.id, channel="whatsapp",
            recipient=PH6, body="Retry test",
            status=MessageStatus.retrying.value,
            attempt_count=3,
            retryable=True,
            idempotency_key=str(uuid.uuid4()),
        )
        db.add(msg)
        db.commit()
        fresh = SessionLocal()
        m = fresh.query(OutreachMessage).filter(OutreachMessage.id == msg.id).first()
        assert m.attempt_count == 3
        assert m.retryable is True
        fresh.close()
        db.delete(msg)
        db.delete(campaign)
        db.delete(lead)
        db.commit()


# ── 16. WhatsApp provider mock transport ─────────────────────────

class TestWhatsAppProviderMockTransport:
    def _make_provider(self, response_body: dict, status_code: int = 200):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json=response_body)
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        return WhatsAppCloudProvider(client=client)

    @patch("app.outreach.whatsapp_provider.settings")
    def test_template_send_success(self, mock_settings):
        mock_settings.whatsapp_cloud_api_token = "test_token"
        mock_settings.whatsapp_cloud_phone_number_id = "12345"
        mock_settings.whatsapp_graph_api_version = "v23.0"
        mock_settings.whatsapp_request_timeout_seconds = 30
        mock_settings.whatsapp_app_secret = ""

        provider = self._make_provider({
            "messages": [{"id": "wamid.ok123"}]
        })
        result = provider.send(
            recipient=PH1, body="Hello",
            template_name="test_template", language_code="ru",
        )
        assert result.success is True
        assert result.provider_message_id == "wamid.ok123"

    @patch("app.outreach.whatsapp_provider.settings")
    def test_free_form_outside_window_rejected(self, mock_settings):
        mock_settings.whatsapp_cloud_api_token = "test_token"
        mock_settings.whatsapp_cloud_phone_number_id = "12345"
        mock_settings.whatsapp_graph_api_version = "v23.0"
        mock_settings.whatsapp_request_timeout_seconds = 30
        mock_settings.whatsapp_app_secret = ""

        provider = self._make_provider({})
        result = provider.send(
            recipient=PH1, body="Hello",
            service_window_active=False,
        )
        assert result.success is False
        assert result.error_code == "service_window_closed"

    @patch("app.outreach.whatsapp_provider.settings")
    def test_free_form_inside_window_sends(self, mock_settings):
        mock_settings.whatsapp_cloud_api_token = "test_token"
        mock_settings.whatsapp_cloud_phone_number_id = "12345"
        mock_settings.whatsapp_graph_api_version = "v23.0"
        mock_settings.whatsapp_request_timeout_seconds = 30
        mock_settings.whatsapp_app_secret = ""

        provider = self._make_provider({
            "messages": [{"id": "wamid.free123"}]
        })
        result = provider.send(
            recipient=PH1, body="Hello!",
            service_window_active=True,
        )
        assert result.success is True
        assert result.provider_message_id == "wamid.free123"

    @patch("app.outreach.whatsapp_provider.settings")
    def test_429_retryable(self, mock_settings):
        mock_settings.whatsapp_cloud_api_token = "test_token"
        mock_settings.whatsapp_cloud_phone_number_id = "12345"
        mock_settings.whatsapp_graph_api_version = "v23.0"
        mock_settings.whatsapp_request_timeout_seconds = 30
        mock_settings.whatsapp_app_secret = ""

        provider = self._make_provider(
            {"error": {"message": "Rate limited", "code": 32}},
            status_code=429,
        )
        result = provider.send(
            recipient=PH1, body="Hello",
            template_name="test", service_window_active=True,
        )
        assert result.success is False
        assert result.retryable is True

    @patch("app.outreach.whatsapp_provider.settings")
    def test_401_permanent(self, mock_settings):
        mock_settings.whatsapp_cloud_api_token = "bad_token"
        mock_settings.whatsapp_cloud_phone_number_id = "12345"
        mock_settings.whatsapp_graph_api_version = "v23.0"
        mock_settings.whatsapp_request_timeout_seconds = 30
        mock_settings.whatsapp_app_secret = ""

        provider = self._make_provider(
            {"error": {"message": "Invalid token", "code": 190}},
            status_code=401,
        )
        result = provider.send(
            recipient=PH1, body="Hello",
            template_name="test", service_window_active=True,
        )
        assert result.success is False
        assert result.retryable is False


# ── 17. Outreach provider send interface ─────────────────────────

class TestProviderInterface:
    def test_mock_provider_send(self):
        from app.outreach.mock_provider import MockOutreachProvider
        provider = MockOutreachProvider()
        result = provider.send(recipient=PH1, body="Test")
        assert result.success is True
        assert result.provider_message_id is not None

    def test_mock_provider_get_status(self):
        from app.outreach.mock_provider import MockOutreachProvider
        provider = MockOutreachProvider()
        status = provider.get_status("wamid.test")
        assert status is not None


# ── 18. Audit log records ────────────────────────────────────────

class TestAuditLogging:
    def test_audit_event_created(self, db):
        from app.security import log_audit_event
        from app.models.audit import AuditLog
        log_audit_event(db, "test_action", "test_entity", "test_123",
                        actor="test_user", details={"key": "value"})
        entry = db.query(AuditLog).filter(AuditLog.entity_id == "test_123").first()
        assert entry is not None
        assert entry.action == "test_action"
        db.delete(entry)
        db.commit()


# ── 19. Stage transitions ────────────────────────────────────────

class TestStageTransitions:
    def test_valid_transition(self, db):
        from app.outreach.stage_service import transition_lead_stage
        lead = Lead(
            name="Stage Test", city="Almaty", phone=PH3,
            status=LeadStatus.enriched.value, stage="needs_review",
        )
        db.add(lead)
        db.commit()
        result = transition_lead_stage(db, lead.id, "ready_for_outreach", "test", "System")
        assert result.stage == "ready_for_outreach"

    def test_invalid_transition_raises(self, db):
        from app.outreach.stage_service import transition_lead_stage
        lead = Lead(
            name="Bad Stage", city="Almaty", phone=PH4,
            status=LeadStatus.enriched.value, stage="new",
        )
        db.add(lead)
        db.commit()
        with pytest.raises(ValueError):
            transition_lead_stage(db, lead.id, "won", "test", "System")


# ── 20. Config production validation ─────────────────────────────

class TestConfigValidation:
    def test_production_requires_whatsapp_secrets(self):
        from pydantic import ValidationError
        from app.config import Settings
        with pytest.raises(ValidationError):
            Settings(
                app_env="test_validation",
                outreach_mode="production",
                outreach_provider="whatsapp",
                whatsapp_cloud_api_token="",
                whatsapp_cloud_phone_number_id="",
                whatsapp_webhook_verify_token="",
                whatsapp_app_secret="",
                admin_password="test123",
                _env_file=None,
            )

    def test_sandbox_mode_no_secrets_required(self):
        from app.config import Settings
        s = Settings(
            app_env="test_sandbox",
            outreach_mode="sandbox",
            outreach_provider="mock",
            admin_password="test123",
            _env_file=None,
        )
        assert s.outreach_mode == "sandbox"
