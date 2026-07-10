import json
import pytest
from datetime import datetime, timezone

from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import (
    ChangeSource,
    LandingPage,
    LandingPageVersion,
    LandingStatus,
    ReviewStatus,
)
from app.models.lead import Lead


class TestContentGenerationModel:
    def test_create_generation(self, db):
        lead = Lead(name="TestCo", city="Алматы", category="Мебель")
        db.add(lead)
        db.flush()

        gen = ContentGeneration(
            id="gen-001",
            lead_id=lead.id,
            provider="template",
            prompt_version="v1",
            status=ContentGenerationStatus.queued.value,
            language="ru",
        )
        db.add(gen)
        db.commit()
        db.refresh(gen)

        assert gen.id == "gen-001"
        assert gen.lead_id == lead.id
        assert gen.provider == "template"
        assert gen.status == "queued"
        assert gen.language == "ru"
        assert gen.created_at is not None

    def test_generation_status_transitions(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        gen = ContentGeneration(
            id="gen-002",
            lead_id=lead.id,
            provider="template",
            prompt_version="v1",
            status=ContentGenerationStatus.queued.value,
        )
        db.add(gen)
        db.commit()

        gen.status = ContentGenerationStatus.running.value
        gen.started_at = datetime.now(timezone.utc)
        db.commit()

        gen.status = ContentGenerationStatus.succeeded.value
        gen.completed_at = datetime.now(timezone.utc)
        gen.output_json = json.dumps({"test": True})
        db.commit()
        db.refresh(gen)

        assert gen.status == "succeeded"
        assert gen.started_at is not None
        assert gen.completed_at is not None

    def test_generation_rejection(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        gen = ContentGeneration(
            id="gen-003",
            lead_id=lead.id,
            provider="template",
            prompt_version="v1",
            status=ContentGenerationStatus.rejected.value,
            validation_errors_json=json.dumps({"errors": ["bad claim"]}),
        )
        db.add(gen)
        db.commit()
        db.refresh(gen)

        assert gen.status == "rejected"
        errors = json.loads(gen.validation_errors_json)
        assert "bad claim" in errors["errors"]


class TestLandingPageVersionModel:
    def test_create_version(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        landing = LandingPage(
            id="lp-001",
            lead_id=lead.id,
            slug="test-slug",
            review_status=ReviewStatus.draft.value,
        )
        db.add(landing)
        db.flush()

        version = LandingPageVersion(
            id="v-001",
            landing_page_id=landing.id,
            version_number=1,
            profile_json=json.dumps({"meta": {"title": "v1"}}),
            change_source=ChangeSource.template.value,
            change_note="Initial generation",
        )
        db.add(version)
        landing.current_version = 1
        db.commit()

        db.refresh(landing)
        assert landing.current_version == 1

        versions = (
            db.query(LandingPageVersion)
            .filter(LandingPageVersion.landing_page_id == landing.id)
            .all()
        )
        assert len(versions) == 1
        assert versions[0].version_number == 1
        assert versions[0].change_source == "template"

    def test_version_ordering(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        landing = LandingPage(
            id="lp-002",
            lead_id=lead.id,
            slug="test-slug-2",
        )
        db.add(landing)
        db.flush()

        for i in range(1, 4):
            v = LandingPageVersion(
                id=f"v-{i}",
                landing_page_id=landing.id,
                version_number=i,
                change_source=ChangeSource.manual.value if i > 1 else ChangeSource.template.value,
                profile_json=json.dumps({"v": i}),
            )
            db.add(v)
        landing.current_version = 3
        db.commit()

        versions = (
            db.query(LandingPageVersion)
            .filter(LandingPageVersion.landing_page_id == landing.id)
            .order_by(LandingPageVersion.version_number.desc())
            .all()
        )
        assert len(versions) == 3
        assert versions[0].version_number == 3
        assert versions[2].version_number == 1

    def test_restore_creates_new_version(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        landing = LandingPage(
            id="lp-003",
            lead_id=lead.id,
            slug="test-slug-3",
            current_version=2,
        )
        db.add(landing)

        v1 = LandingPageVersion(
            id="v-r1",
            landing_page_id=landing.id,
            version_number=1,
            profile_json=json.dumps({"meta": {"title": "v1"}}),
            change_source=ChangeSource.template.value,
        )
        v2 = LandingPageVersion(
            id="v-r2",
            landing_page_id=landing.id,
            version_number=2,
            profile_json=json.dumps({"meta": {"title": "v2"}}),
            change_source=ChangeSource.manual.value,
        )
        db.add(v1)
        db.add(v2)
        db.commit()

        restored_v1 = (
            db.query(LandingPageVersion)
            .filter(
                LandingPageVersion.landing_page_id == landing.id,
                LandingPageVersion.version_number == 1,
            )
            .first()
        )

        new_version = LandingPageVersion(
            id="v-r3",
            landing_page_id=landing.id,
            version_number=3,
            profile_json=restored_v1.profile_json,
            change_source=ChangeSource.manual.value,
            change_note="Restored from v1",
        )
        db.add(new_version)
        landing.profile_json = restored_v1.profile_json
        landing.current_version = 3
        db.commit()

        db.refresh(landing)
        assert landing.current_version == 3
        assert landing.profile_json == restored_v1.profile_json


class TestReviewWorkflow:
    def test_draft_to_needs_review(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        landing = LandingPage(
            id="lp-wf1",
            lead_id=lead.id,
            slug="wf-slug",
            review_status=ReviewStatus.draft.value,
        )
        db.add(landing)
        db.commit()
        db.refresh(landing)

        assert landing.review_status == "draft"

        landing.review_status = ReviewStatus.needs_review.value
        db.commit()
        db.refresh(landing)
        assert landing.review_status == "needs_review"

    def test_needs_review_to_approved(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        landing = LandingPage(
            id="lp-wf2",
            lead_id=lead.id,
            slug="wf-slug-2",
            review_status=ReviewStatus.needs_review.value,
        )
        db.add(landing)
        db.commit()

        landing.review_status = ReviewStatus.approved.value
        landing.status = LandingStatus.approved.value
        landing.approved_at = datetime.now(timezone.utc)
        landing.approved_by = "admin"
        db.commit()
        db.refresh(landing)

        assert landing.review_status == "approved"
        assert landing.approved_by == "admin"

    def test_needs_review_to_rejected(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        landing = LandingPage(
            id="lp-wf3",
            lead_id=lead.id,
            slug="wf-slug-3",
            review_status=ReviewStatus.needs_review.value,
        )
        db.add(landing)
        db.commit()

        landing.review_status = ReviewStatus.rejected.value
        landing.status = LandingStatus.failed.value
        landing.review_note = "Слишком общие преимущества"
        db.commit()
        db.refresh(landing)

        assert landing.review_status == "rejected"
        assert landing.review_note == "Слишком общие преимущества"

    def test_approved_to_published(self, db):
        lead = Lead(name="Co", city="City", category="Cat")
        db.add(lead)
        db.flush()

        landing = LandingPage(
            id="lp-wf4",
            lead_id=lead.id,
            slug="wf-slug-4",
            review_status=ReviewStatus.approved.value,
            status=LandingStatus.approved.value,
        )
        db.add(landing)
        db.commit()

        landing.review_status = ReviewStatus.published.value
        landing.status = LandingStatus.published.value
        db.commit()
        db.refresh(landing)

        assert landing.review_status == "published"
