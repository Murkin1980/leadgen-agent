import pytest
from app.enrichment.enricher import (
    normalize_phone,
    make_whatsapp_url,
    make_slug,
    classify_specialization,
    build_services,
    enrich_lead,
)
from app.models.lead import Lead


class TestPhoneNormalization:
    def test_kazakhstan_format(self):
        assert normalize_phone("+77001112233") == "+77001112233"

    def test_eight_start(self):
        assert normalize_phone("87001112233") == "+77001112233"

    def test_ten_digits(self):
        assert normalize_phone("7001112233") == "+77001112233"

    def test_with_dashes(self):
        assert normalize_phone("+7 (700) 111-22-33") == "+77001112233"

    def test_none_returns_none(self):
        assert normalize_phone(None) is None

    def test_empty_string(self):
        assert normalize_phone("") is None


class TestWhatsAppUrl:
    def test_creates_wa_link(self):
        url = make_whatsapp_url("+77001112233")
        assert url == "https://wa.me/77001112233"

    def test_none_phone(self):
        assert make_whatsapp_url(None) is None


class TestSlug:
    def test_basic_slug(self):
        slug = make_slug("Mebel Art", "Алматы")
        assert len(slug) >= 3
        assert " " not in slug
        assert slug == slug.lower()

    def test_no_special_chars(self):
        slug = make_slug("Тест & Co.", "Алматы")
        assert "&" not in slug
        assert "." not in slug

    def test_no_cyrillic_in_slug(self):
        slug = make_slug("Mebel Art", "Алматы")
        for ch in slug:
            assert ch.isascii() or ch == "-"

    def test_min_length(self):
        slug = make_slug("A", "B")
        assert len(slug) >= 3


class TestSpecialization:
    def test_kitchen(self):
        spec = classify_specialization("Кухни Мастер", "Мебель на заказ")
        assert "кухон" in spec.lower()

    def test_wardrobe(self):
        spec = classify_specialization("Гардеробная", "Мебель на заказ")
        assert "гардероб" in spec.lower()

    def test_office(self):
        spec = classify_specialization("ОфисМебель", "Офисная мебель")
        assert "офис" in spec.lower()

    def test_default(self):
        spec = classify_specialization("Универсал", "Мебель")
        assert "мебел" in spec.lower()


class TestEnrichLead:
    def test_returns_dict(self):
        lead = Lead(
            name="Mebel Art",
            city="Алматы",
            category="Мебель на заказ",
            phone="+77001112233",
        )
        result = enrich_lead(lead)
        assert isinstance(result, dict)
        assert result["company_name"] == "Mebel Art"
        assert result["city"] == "Алматы"
        assert result["phone"] == "+77001112233"
        assert result["whatsapp_url"] == "https://wa.me/77001112233"
        assert result["slug"]
        assert len(result["services"]) > 0
        assert len(result["advantages"]) > 0
