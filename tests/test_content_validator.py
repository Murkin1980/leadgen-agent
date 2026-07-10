import json
import pytest

from app.generation.base import GeneratedProfile, GeneratedProfileClaim
from app.generation.context import GenerationContext
from app.generation.validator import GeneratedContentValidator, ValidationResult
from app.generation.mock import MockTextGenerationAdapter


class TestValidatorSchemaChecks:
    def _make_valid_profile(self):
        adapter = MockTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="TestCo",
            city="Алматы",
            category="Мебель",
            phone="+77001112233",
            language="ru",
        )
        return adapter.generate(ctx), ctx

    def test_valid_profile_passes(self):
        profile, ctx = self._make_valid_profile()
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_missing_meta_fails(self):
        profile, ctx = self._make_valid_profile()
        profile.data.pop("meta", None)
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid
        assert any("meta" in e for e in result.errors)

    def test_missing_hero_fails(self):
        profile, ctx = self._make_valid_profile()
        profile.data.pop("hero", None)
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid
        assert any("hero" in e for e in result.errors)

    def test_empty_hero_title_fails(self):
        profile, ctx = self._make_valid_profile()
        profile.data["hero"]["title"] = ""
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid

    def test_empty_cta_fails(self):
        profile, ctx = self._make_valid_profile()
        profile.data["hero"]["cta_text"] = ""
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid


class TestValidatorPhoneConsistency:
    def _make_ctx(self, phone="+77001112233"):
        return GenerationContext(
            company_name="Co", city="City", category="Cat", phone=phone
        )

    def test_matching_phones_pass(self):
        adapter = MockTextGenerationAdapter()
        ctx = self._make_ctx()
        profile = adapter.generate(ctx)
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert result.is_valid

    def test_mismatched_phones_fail(self):
        profile = GeneratedProfile(
            data={
                "meta": {"title": "T", "description": "D"},
                "company": {"name": "Co", "city": "City", "phone": "+77009998877", "whatsapp_url": ""},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "CTA"},
                "contacts": {"phone": "+77009998877"},
                "services": [],
                "advantages": [],
            }
        )
        ctx = self._make_ctx(phone="+77001112233")
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid
        assert any("Phone does not match" in e for e in result.errors)


class TestValidatorCityConsistency:
    def test_mismatched_city_fails(self):
        profile = GeneratedProfile(
            data={
                "meta": {"title": "T", "description": "D"},
                "company": {"name": "Co", "city": "Нур-Султан"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "CTA"},
                "contacts": {"phone": "+7700"},
                "services": [],
                "advantages": [],
            }
        )
        ctx = GenerationContext(
            company_name="Co", city="Алматы", category="Cat"
        )
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid
        assert any("City mismatch" in e for e in result.errors)

    def test_matching_city_passes(self):
        adapter = MockTextGenerationAdapter()
        ctx = GenerationContext(
            company_name="Co", city="Алматы", category="Cat"
        )
        profile = adapter.generate(ctx)
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert result.is_valid


class TestValidatorForbiddenContent:
    def test_html_tags_fail(self):
        profile = GeneratedProfile(
            data={
                "meta": {"title": "T <b>bold</b>", "description": "D"},
                "company": {"name": "Co", "city": "City"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "CTA"},
                "contacts": {},
                "services": [{"title": "S1", "description": "<script>alert(1)</script>"}],
                "advantages": [],
            }
        )
        ctx = GenerationContext(company_name="Co", city="City", category="Cat")
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid

    def test_script_tags_fail(self):
        profile = GeneratedProfile(
            data={
                "meta": {"title": "T", "description": "D"},
                "company": {"name": "Co", "city": "City"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "CTA"},
                "contacts": {},
                "services": [],
                "advantages": ["<script>bad</script>"],
            }
        )
        ctx = GenerationContext(company_name="Co", city="City", category="Cat")
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid

    def test_api_key_in_output_fails(self):
        profile = GeneratedProfile(
            data={
                "meta": {"title": "sk-abc123def456", "description": "D"},
                "company": {"name": "Co", "city": "City"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "CTA"},
                "contacts": {},
                "services": [],
                "advantages": [],
            }
        )
        ctx = GenerationContext(company_name="Co", city="City", category="Cat")
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid

    def test_unsupported_claim_rejected(self):
        profile = GeneratedProfile(
            data={
                "meta": {"title": "T", "description": "D"},
                "company": {"name": "Co", "city": "City"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "CTA"},
                "contacts": {},
                "services": [],
                "advantages": [],
                "claims": [
                    {"text": "10 лет опыта", "source_field": "unknown", "verified": False}
                ],
            }
        )
        ctx = GenerationContext(company_name="Co", city="City", category="Cat")
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid
        assert any("Unsupported claim" in e for e in result.errors)


class TestValidatorDuplicateServices:
    def test_duplicate_services_fail(self):
        profile = GeneratedProfile(
            data={
                "meta": {"title": "T", "description": "D"},
                "company": {"name": "Co", "city": "City"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "CTA"},
                "contacts": {},
                "services": [
                    {"title": "Услуга", "description": "D1"},
                    {"title": "услуга", "description": "D2"},
                ],
                "advantages": [],
            }
        )
        ctx = GenerationContext(company_name="Co", city="City", category="Cat")
        validator = GeneratedContentValidator()
        result = validator.validate(profile, ctx)
        assert not result.is_valid
        assert any("Duplicate service" in e for e in result.errors)


class TestValidatorFieldLength:
    def test_oversized_field_fails(self):
        profile = GeneratedProfile(
            data={
                "meta": {"title": "x" * 3000, "description": "D"},
                "company": {"name": "Co", "city": "City"},
                "hero": {"title": "H", "subtitle": "S", "cta_text": "CTA"},
                "contacts": {},
                "services": [],
                "advantages": [],
            }
        )
        ctx = GenerationContext(company_name="Co", city="City", category="Cat")
        validator = GeneratedContentValidator(max_field_length=2000)
        result = validator.validate(profile, ctx)
        assert not result.is_valid
        assert any("exceeds max length" in e for e in result.errors)
