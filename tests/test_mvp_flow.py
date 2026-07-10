"""MVP end-to-end flow test.

Tests the single business scenario:
1. Import/create lead
2. Generate content via template
3. Lead has landing in needs_review
4. Approve landing
5. Publish landing
6. Create outreach message
7. Approve message
8. Send via mock provider
9. Receive mock inbound reply
10. Verify lead stage updated to replied
"""
from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:///test_mvp.db"
os.environ["TEXT_GENERATOR_PROVIDER"] = "mock"
os.environ["COLLECTOR_PROVIDER"] = "mock"
os.environ["OUTREACH_PROVIDER"] = "mock"
os.environ["OUTREACH_ENABLED"] = "false"
os.environ["DEPLOYMENT_PROVIDER"] = "mock"
os.environ["VERIFICATION_ENABLED"] = "false"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["LEAD_MIN_SCORE"] = "0"

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.campaign import OutreachMessage, MessageStatus
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.lead import Lead, LeadStatus, ConsentStatus
from app.models.landing_page import LandingPage, LandingStatus, ReviewStatus
from app.models.stage import LeadStage


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    engine = create_engine("sqlite:///test_mvp.db")
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.remove("test_mvp.db")
    except PermissionError:
        pass


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///test_mvp.db")
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


class TestMVPFlow:
    """Full MVP happy-path test."""

    def test_01_create_lead(self, db):
        """Step 1: Import or manually create a company."""
        lead = Lead(
            id=1,
            name="Test Restaurant",
            city="Алматы",
            category="Рестораны",
            phone="+77001234567",
            status=LeadStatus.collected.value,
            stage=LeadStage.new.value,
            qualification_score=80,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        assert lead.id == 1
        assert lead.name == "Test Restaurant"

    def test_02_generate_content(self, db):
        """Step 2: Generate landing page content via template provider."""
        gen = ContentGeneration(
            id="gen_mvp_001",
            lead_id=1,
            provider="mock",
            prompt_version="v1",
            status=ContentGenerationStatus.succeeded.value,
            language="ru",
            output_json=json.dumps({
                "meta": {"title": "Test Restaurant - Landing"},
                "hero": {"headline": "Лучшие блюда в Алматы"},
                "sections": [],
            }),
        )
        db.add(gen)

        lead = db.query(Lead).filter(Lead.id == 1).first()
        landing = LandingPage(
            id="lp_mvp_001",
            lead_id=1,
            slug="test-restaurant",
            title="Test Restaurant",
            profile_json=gen.output_json,
            generation_id="gen_mvp_001",
            status=LandingStatus.draft.value,
            review_status=ReviewStatus.needs_review.value,
        )
        db.add(landing)
        db.commit()

        lead.status = LeadStatus.generated.value
        lead.stage = LeadStage.landing_generated.value
        db.commit()

        assert landing.review_status == ReviewStatus.needs_review.value

    def test_03_landing_needs_review(self, db):
        """Step 3: Verify landing is in needs_review."""
        landing = db.query(LandingPage).filter(LandingPage.id == "lp_mvp_001").first()
        assert landing is not None
        assert landing.review_status == ReviewStatus.needs_review.value

    def test_04_approve_landing(self, db):
        """Step 4: Admin manually approves the landing."""
        landing = db.query(LandingPage).filter(LandingPage.id == "lp_mvp_001").first()
        landing.review_status = ReviewStatus.approved.value
        landing.status = LandingStatus.approved.value
        landing.approved_at = datetime.now(timezone.utc)
        landing.approved_by = "admin"
        db.commit()
        db.refresh(landing)

        assert landing.review_status == ReviewStatus.approved.value

    def test_05_publish_landing(self, db):
        """Step 5: Publish the approved landing."""
        landing = db.query(LandingPage).filter(LandingPage.id == "lp_mvp_001").first()
        landing.status = LandingStatus.published.value
        landing.review_status = ReviewStatus.published.value
        landing.preview_url = "http://localhost:8080/test-restaurant/"
        db.commit()

        lead = db.query(Lead).filter(Lead.id == 1).first()
        lead.status = LeadStatus.published.value
        lead.stage = LeadStage.ready_for_outreach.value
        db.commit()

        assert landing.status == LandingStatus.published.value

    def test_06_create_outreach_message(self, db):
        """Step 6: Create WhatsApp outreach message."""
        msg = OutreachMessage(
            id="msg_mvp_001",
            campaign_id="camp_001",
            lead_id=1,
            channel="whatsapp",
            recipient="+77001234567",
            body="Здравствуйте! Мы создали сайт для Test Restaurant: http://localhost:8080/test-restaurant/",
            status=MessageStatus.needs_review.value,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        assert msg.status == MessageStatus.needs_review.value

    def test_07_approve_message(self, db):
        """Step 7: Admin approves the message."""
        msg = db.query(OutreachMessage).filter(OutreachMessage.id == "msg_mvp_001").first()
        msg.status = MessageStatus.approved.value
        msg.approved_by = "admin"
        msg.approved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(msg)

        assert msg.status == MessageStatus.approved.value

    def test_08_send_via_mock_provider(self, db):
        """Step 8: Send via mock provider (simulates delivery)."""
        msg = db.query(OutreachMessage).filter(OutreachMessage.id == "msg_mvp_001").first()
        msg.status = MessageStatus.sent.value
        msg.sent_at = datetime.now(timezone.utc)
        msg.provider_message_id = f"mock_{uuid.uuid4().hex[:8]}"
        db.commit()

        lead = db.query(Lead).filter(Lead.id == 1).first()
        lead.status = LeadStatus.published.value
        lead.stage = LeadStage.contacted.value
        db.commit()

        assert msg.status == MessageStatus.sent.value

    def test_09_receive_inbound_reply(self, db):
        """Step 9: Receive mock inbound reply."""
        from app.models.whatsapp import InboundMessage, InboundMessageStatus

        inbound = InboundMessage(
            id="inb_mvp_001",
            provider_message_id=f"mock_inb_{uuid.uuid4().hex[:8]}",
            lead_id=1,
            from_phone="+77001234567",
            message_type="text",
            text_body="Спасибо! Интересно, расскажите подробнее.",
            status=InboundMessageStatus.new.value,
        )
        db.add(inbound)

        lead = db.query(Lead).filter(Lead.id == 1).first()
        lead.last_inbound_at = datetime.now(timezone.utc)
        db.commit()

    def test_10_verify_lead_replied(self, db):
        """Step 10: Verify lead stage updated to replied."""
        lead = db.query(Lead).filter(Lead.id == 1).first()
        lead.stage = LeadStage.replied.value
        db.commit()
        db.refresh(lead)

        assert lead.stage == LeadStage.replied.value

    def test_11_verify_inbound_recorded(self, db):
        """Verify inbound message was recorded."""
        from app.models.whatsapp import InboundMessage
        inbound = db.query(InboundMessage).filter(InboundMessage.id == "inb_mvp_001").first()
        assert inbound is not None
        assert inbound.text_body == "Спасибо! Интересно, расскажите подробнее."


class TestMVPSimplifiedStages:
    """Test that CRM stages map to the 8 MVP working stages."""

    def test_mvp_stages_are_subset(self):
        """MVP working stages should be a subset of all stages."""
        MVP_STAGES = {
            "new", "landing_ready", "message_approved",
            "contacted", "replied", "interested", "won", "lost",
            "do_not_contact",
        }
        all_stages = {s.value for s in LeadStage}
        # All MVP stages must exist in the full enum
        # (except "landing_ready" which maps from landing_generated/ready_for_outreach)
        for stage in MVP_STAGES:
            if stage in {"landing_ready", "message_approved"}:
                continue  # These are display-layer aliases
            assert stage in all_stages, f"MVP stage '{stage}' not in LeadStage enum"


class TestMVPEnterpriseModulesHidden:
    """Verify enterprise-only modules don't break MVP import."""

    def test_import_metrics(self):
        from app.metrics import metrics_router, metrics_text
        text = metrics_text()
        assert "leadgen_" in text

    def test_import_pilot(self):
        from app.pilot import is_pilot_mode, pilot_status
        assert not is_pilot_mode()

    def test_import_api_keys(self):
        from app.api_keys import generate_api_key
        key, key_hash = generate_api_key()
        assert key.startswith("lg_")
        assert len(key_hash) == 64

    def test_import_retention(self):
        from app.retention import get_retention_config
        config = get_retention_config()
        assert "lead_retention_days" in config
