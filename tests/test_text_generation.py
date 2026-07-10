import json
import pytest
from unittest.mock import MagicMock, patch

from app.generation.base import GeneratedProfile, GeneratedProfileClaim
from app.generation.context import GenerationContext
from app.generation.factory import create_text_generator, get_available_text_providers
from app.generation.mock import MockTextGenerationAdapter
from app.generation.template import TemplateTextGenerationAdapter
from app.models.lead import Lead


class TestTextProviderFactory:
    def test_returns_template_by_default(self):
        gen = create_text_generator("template")
        assert isinstance(gen, TemplateTextGenerationAdapter)

    def test_returns_mock(self):
        gen = create_text_generator("mock")
        assert isinstance(gen, MockTextGenerationAdapter)

    def test_returns_template_for_unknown(self):
        gen = create_text_generator("unknown")
        assert isinstance(gen, TemplateTextGenerationAdapter)

    def test_available_providers_includes_template_and_mock(self):
        providers = get_available_text_providers()
        assert "template" in providers
        assert "mock" in providers


class TestMockTextGenerationAdapter:
    def test_generates_profile(self):
        adapter = MockTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="TestCo",
            city="Алматы",
            category="Мебель",
            phone="+77001112233",
            language="ru",
        )
        result = adapter.generate(ctx)
        assert isinstance(result, GeneratedProfile)
        assert result.data["company"]["name"] == "TestCo"
        assert result.data["company"]["city"] == "Алматы"
        assert result.data["language"] == "ru"
        assert len(result.claims) > 0

    def test_kazakh_language(self):
        adapter = MockTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="TestCo",
            city="Алматы",
            category="Мебель",
            language="kk",
        )
        result = adapter.generate(ctx)
        assert result.data["language"] == "kk"
        assert "бағаны" in result.data["hero"]["cta_text"].lower() or "есептеу" in result.data["hero"]["cta_text"].lower()

    def test_increments_call_count(self):
        adapter = MockTextGenerationAdapter()
        ctx = GenerationContext(company_name="Co", city="City", category="Cat")
        assert adapter.call_count == 0
        adapter.generate(ctx)
        assert adapter.call_count == 1
        adapter.generate(ctx)
        assert adapter.call_count == 2


class TestTemplateTextGenerationAdapter:
    def test_generates_ru_profile(self):
        adapter = TemplateTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="Мебель-Мастер",
            city="Алматы",
            category="Кухни на заказ",
            phone="+77001112233",
            language="ru",
        )
        result = adapter.generate(ctx)
        assert result.data["language"] == "ru"
        assert "Мебель-Мастер" in result.data["company"]["name"]
        assert "Алматы" in result.data["company"]["city"]
        assert len(result.data["services"]) > 0
        assert len(result.data["advantages"]) > 0
        assert len(result.data["work_stages"]) > 0
        assert len(result.data["faq"]) > 0

    def test_generates_kk_profile(self):
        adapter = TemplateTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="Мебель-Мастер",
            city="Алматы",
            category="Кухни на заказ",
            phone="+77001112233",
            language="kk",
        )
        result = adapter.generate(ctx)
        assert result.data["language"] == "kk"
        assert len(result.data["services"]) > 0
        assert result.data["hero"]["cta_text"]

    def test_claims_include_verified_data(self):
        adapter = TemplateTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="TestCo",
            city="Алматы",
            category="Мебель",
            phone="+77001112233",
            rating=4.8,
            reviews_count=25,
        )
        result = adapter.generate(ctx)
        verified_claims = [c for c in result.claims if c.verified]
        assert len(verified_claims) >= 2
        assert any("Мебель-Мастер" in c.text or "TestCo" in c.text for c in result.claims)

    def test_empty_services_fallback(self):
        adapter = TemplateTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="Co",
            city="City",
            category="Непонятная категория",
        )
        result = adapter.generate(ctx)
        assert len(result.data["services"]) > 0

    def test_explicit_services_override(self):
        adapter = TemplateTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="Co",
            city="City",
            category="Мебель",
            services=["Custom Service 1", "Custom Service 2"],
        )
        result = adapter.generate(ctx)
        titles = [s["title"] for s in result.data["services"]]
        assert "Custom Service 1" in titles
        assert "Custom Service 2" in titles


class TestGenerationContext:
    def test_from_lead(self):
        lead = Lead(
            name="TestCo",
            city="Алматы",
            category="Мебель",
            phone="+77001112233",
            whatsapp="+77001112233",
            instagram="https://instagram.com/test",
            telegram="https://t.me/test",
            rating=4.5,
            reviews_count=10,
            address="ул. Тестовая, 1",
            source="mock",
            source_id="mock-1",
            source_url="http://example.com",
        )
        ctx = GenerationContext.from_lead(lead, qualification_reasons=["Has phone"])
        assert ctx.company_name == "TestCo"
        assert ctx.city == "Алматы"
        assert ctx.phone == "+77001112233"
        assert ctx.whatsapp_url == "+77001112233"
        assert ctx.rating == 4.5
        assert ctx.reviews_count == 10
        assert ctx.address == "ул. Тестовая, 1"
        assert "https://instagram.com/test" in ctx.social_links
        assert "https://t.me/test" in ctx.social_links
        assert ctx.qualification_reasons == ["Has phone"]
        assert ctx.source_metadata["source"] == "mock"

    def test_from_lead_minimal(self):
        lead = Lead(name="Co", city="City")
        ctx = GenerationContext.from_lead(lead)
        assert ctx.company_name == "Co"
        assert ctx.phone is None
        assert ctx.social_links == []


class TestGeneratedProfile:
    def test_to_dict(self):
        claim = GeneratedProfileClaim(text="Test", source_field="name", verified=True)
        profile = GeneratedProfile(data={"meta": {"title": "T"}}, claims=[claim])
        d = profile.to_dict()
        assert d["meta"]["title"] == "T"
        assert len(d["claims"]) == 1
        assert d["claims"][0]["text"] == "Test"

    def test_from_dict(self):
        d = {
            "meta": {"title": "T"},
            "claims": [{"text": "X", "source_field": "y", "verified": True}],
        }
        profile = GeneratedProfile.from_dict(d)
        assert profile.data["meta"]["title"] == "T"
        assert len(profile.claims) == 1
        assert profile.claims[0].source_field == "y"

    def test_claim_to_dict(self):
        claim = GeneratedProfileClaim(text="A", source_field="b", verified=False)
        d = claim.to_dict()
        assert d == {"text": "A", "source_field": "b", "verified": False}
