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

    def test_cyrillic_name_is_transliterated_not_dropped(self):
        # Regression test: fully Cyrillic name/city used to fall through to
        # the "company" placeholder because SLUG_RE only accepts ASCII and
        # nothing transliterated the Cyrillic characters first. That made
        # every Cyrillic-named lead (i.e. almost all real leads) collapse to
        # the same slug and overwrite each other's published landing page.
        slug = make_slug("Дерево Мастер", "Алматы")
        assert slug != "company"
        assert "derevo" in slug
        assert "master" in slug
        assert "almaty" in slug

    def test_two_cyrillic_leads_get_different_slugs(self):
        slug_a = make_slug("Дерево Мастер", "Алматы", unique_id=3)
        slug_b = make_slug("Шкаф Мастер", "Алматы", unique_id=2)
        assert slug_a != slug_b

    def test_same_name_different_ids_are_unique(self):
        slug_a = make_slug("Мебель Сити", "Алматы", unique_id=1)
        slug_b = make_slug("Мебель Сити", "Алматы", unique_id=2)
        assert slug_a != slug_b


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

    def test_slug_includes_lead_id_for_uniqueness(self):
        lead = Lead(
            id=42,
            name="Дерево Мастер",
            city="Алматы",
            category="Мебель на заказ",
            phone="+77001112233",
        )
        result = enrich_lead(lead)
        assert result["slug"].endswith("-42")
        assert result["slug"] != "company"
