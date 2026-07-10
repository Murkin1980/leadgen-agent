import json
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import (
    LandingPage,
    LandingPageVersion,
    LandingStatus,
    ReviewStatus,
)
from app.models.lead import Lead, LeadStatus


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_lead(db):
    lead = Lead(
        name="Тест-Мебель",
        city="Алматы",
        category="Мебель на заказ",
        phone="+77001112233",
        status=LeadStatus.enriched.value,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@pytest.fixture
def sample_landing(db, sample_lead):
    landing_id = str(uuid.uuid4())[:12]
    landing = LandingPage(
        id=landing_id,
        lead_id=sample_lead.id,
        slug=f"test-{landing_id}",
        title="Тестовый лендинг",
        profile_json=json.dumps({
            "meta": {"title": "Test", "description": "Desc"},
            "company": {"name": "Тест-Мебель", "city": "Алматы", "phone": "+77001112233", "whatsapp_url": ""},
            "hero": {"title": "Hero", "subtitle": "Sub", "cta_text": "CTA"},
            "services": [],
            "advantages": [],
            "contacts": {"phone": "+77001112233"},
            "theme": {"style": "modern", "primary_color": "#000", "accent_color": "#fff"},
        }),
        review_status=ReviewStatus.needs_review.value,
        status=LandingStatus.draft.value,
    )
    db.add(landing)
    db.commit()
    db.refresh(landing)
    return landing


class TestCreateContentGeneration:
    @patch("app.api.routes.Queue")
    def test_create_generation(self, mock_queue_cls, client, sample_lead):
        mock_queue = MagicMock()
        mock_queue_cls.return_value = mock_queue

        response = client.post(
            f"/leads/{sample_lead.id}/content-generations",
            json={"language": "ru", "provider": "template"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "template"
        assert data["language"] == "ru"
        assert data["status"] == "queued"

    def test_create_generation_lead_not_found(self, client):
        response = client.post("/leads/99999/content-generations")
        assert response.status_code == 404

    @patch("app.api.routes.Queue")
    def test_create_generation_default_provider(self, mock_queue_cls, client, sample_lead):
        mock_queue = MagicMock()
        mock_queue_cls.return_value = mock_queue

        response = client.post(f"/leads/{sample_lead.id}/content-generations")
        assert response.status_code == 200
        assert response.json()["provider"] == "mock"


class TestListContentGenerations:
    def test_list_empty(self, client):
        response = client.get("/content-generations")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @patch("app.api.routes.Queue")
    def test_list_with_generations(self, mock_queue_cls, client, sample_lead, db):
        mock_queue = MagicMock()
        mock_queue_cls.return_value = mock_queue

        for _ in range(2):
            gen = ContentGeneration(
                id=str(uuid.uuid4())[:12],
                lead_id=sample_lead.id,
                provider="template",
                prompt_version="v1",
                status="succeeded",
            )
            db.add(gen)
        db.commit()

        response = client.get("/content-generations")
        assert response.status_code == 200
        assert len(response.json()) >= 2

    def test_filter_by_lead_id(self, client, db, sample_lead):
        gen = ContentGeneration(
            id=str(uuid.uuid4())[:12],
            lead_id=sample_lead.id,
            provider="template",
            prompt_version="v1",
            status="succeeded",
        )
        db.add(gen)
        db.commit()

        response = client.get(f"/content-generations?lead_id={sample_lead.id}")
        assert response.status_code == 200
        assert len(response.json()) >= 1


class TestLandingApproval:
    def test_approve_landing(self, client, sample_landing):
        response = client.post(
            f"/landings/{sample_landing.id}/approve",
            json={"approved_by": "admin"},
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == "approved"
        assert response.json()["approved_by"] == "admin"

    def test_reject_landing(self, client, sample_landing):
        response = client.post(
            f"/landings/{sample_landing.id}/reject",
            json={"reason": "Не подходит"},
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == "rejected"
        assert response.json()["review_note"] == "Не подходит"

    def test_approve_nonexistent(self, client):
        response = client.post("/landings/nonexistent/approve")
        assert response.status_code == 404


class TestLandingVersions:
    def test_list_versions_empty(self, client, sample_landing):
        response = client.get(f"/landings/{sample_landing.id}/versions")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_version_on_edit(self, client, sample_landing, db):
        new_profile = {
            "meta": {"title": "Updated", "description": "New desc"},
            "company": {"name": "Тест-Мебель", "city": "Алматы"},
            "hero": {"title": "New Hero", "subtitle": "Sub", "cta_text": "CTA"},
            "services": [],
            "advantages": [],
            "contacts": {},
            "theme": {"style": "modern", "primary_color": "#000", "accent_color": "#fff"},
        }
        response = client.put(
            f"/landings/{sample_landing.id}/profile",
            content=json.dumps(new_profile),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == "needs_review"
        assert response.json()["current_version"] == 1

        versions = db.query(LandingPageVersion).filter(
            LandingPageVersion.landing_page_id == sample_landing.id
        ).all()
        assert len(versions) == 1
        assert versions[0].change_source == "manual"

    def test_restore_version(self, client, sample_landing, db):
        version = LandingPageVersion(
            id=str(uuid.uuid4())[:12],
            landing_page_id=sample_landing.id,
            version_number=1,
            profile_json=sample_landing.profile_json,
            change_source="template",
        )
        db.add(version)
        sample_landing.current_version = 1
        db.commit()

        response = client.post(
            f"/landings/{sample_landing.id}/versions/1/restore"
        )
        assert response.status_code == 200
        assert response.json()["current_version"] == 2
        assert response.json()["review_status"] == "needs_review"

        versions = db.query(LandingPageVersion).filter(
            LandingPageVersion.landing_page_id == sample_landing.id
        ).order_by(LandingPageVersion.version_number.desc()).all()
        assert len(versions) == 2
        assert versions[0].change_note == "Restored from v1"


class TestPublishingBlocked:
    def test_publish_rejected_landing(self, client, db, sample_lead):
        landing = LandingPage(
            id=str(uuid.uuid4())[:12],
            lead_id=sample_lead.id,
            slug="rejected-slug",
            review_status=ReviewStatus.rejected.value,
            status=LandingStatus.failed.value,
            profile_json=json.dumps({
                "meta": {"title": "T", "description": "D"},
                "company": {"name": "Co", "city": "City"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "C"},
                "contacts": {},
            }),
        )
        db.add(landing)
        db.commit()

        response = client.post(f"/landings/{landing.id}/publish")
        assert response.status_code == 409
        assert "Cannot publish" in response.json()["detail"]

    def test_publish_needs_review_landing(self, client, sample_landing):
        response = client.post(f"/landings/{sample_landing.id}/publish")
        assert response.status_code == 409

    def test_publish_draft_landing(self, client, db, sample_lead):
        landing = LandingPage(
            id=str(uuid.uuid4())[:12],
            lead_id=sample_lead.id,
            slug="draft-slug",
            review_status=ReviewStatus.draft.value,
            profile_json=json.dumps({
                "meta": {"title": "T", "description": "D"},
                "company": {"name": "Co", "city": "City"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "C"},
                "contacts": {},
            }),
        )
        db.add(landing)
        db.commit()

        response = client.post(f"/landings/{landing.id}/publish")
        assert response.status_code == 409


class TestUsageEndpoint:
    def test_usage_summary(self, client):
        response = client.get("/usage/openai")
        assert response.status_code == 200
        data = response.json()
        assert "requests_today" in data
        assert "daily_budget_usd" in data
        assert "remaining_budget_usd" in data
        assert "estimated_cost_usd" in data
