"""
Regression coverage for app.workers.content_generator_worker.

Prior to this test, no test invoked run_content_generator() itself -- only
the API endpoint that enqueues it, and unit tests on GenerationContext in
isolation. That gap let a real bug ship: the worker tried to assign to
fields on the frozen GenerationContext dataclass, which raises
dataclasses.FrozenInstanceError and crashes every single content
generation, regardless of provider or input. This test drives the worker
function directly (as the RQ worker would) to catch that class of bug.
"""

from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import LandingPage
from app.models.lead import Lead
from app.workers.content_generator_worker import run_content_generator


class TestRunContentGenerator:
    def test_succeeds_with_template_provider(self, db):
        lead = Lead(
            name="Дерево Мастер",
            city="Алматы",
            category="Мебель на заказ",
            phone="+77009990011",
            slug="almaty-derevo-master-1",
        )
        db.add(lead)
        db.flush()

        gen = ContentGeneration(
            id="gen-worker-001",
            lead_id=lead.id,
            provider="template",
            prompt_version="v1",
            status=ContentGenerationStatus.queued.value,
            language="ru",
        )
        db.add(gen)
        db.commit()

        run_content_generator(gen.id)

        db.refresh(gen)
        assert gen.status == ContentGenerationStatus.succeeded.value, gen.error_message
        assert gen.error_message is None
        assert gen.landing_page_id is not None

        landing = (
            db.query(LandingPage)
            .filter(LandingPage.id == gen.landing_page_id)
            .first()
        )
        assert landing is not None
        assert landing.slug == lead.slug
