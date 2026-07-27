"""
Kazakhstan/Russian data regression tests.

Required by docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md section 4.6.

Covers the realistic-input cases the doc lists explicitly. Writing these
tests found two more real bugs (in addition to the four already fixed and
the LandingStatus.generated bug found by the E2E test):

- make_slug() had no length cap, so a long company name produced a
  200-300+ character slug -- past the ~255-byte path-component limit on
  most Linux filesystems, which would break mkdir() in save_landing().
- enrich_lead()'s own normalize_phone()/make_whatsapp_url() used a
  separate, looser phone parser that silently passed through garbage
  input (e.g. normalize_phone("abc") returned "abc" unchanged), which
  then produced a broken "https://wa.me/" (or "https://wa.me/123")
  WhatsApp link instead of failing safely. Fixed by reusing the already-
  validated PhoneNumberService normalizer instead of a duplicate
  implementation.
"""

import pytest

from app.enrichment.enricher import enrich_lead, make_slug, make_whatsapp_url, normalize_phone
from app.models.lead import Lead
from app.outreach.phone import PhoneNumberError, PhoneNumberService


class TestKazakhCompanyNameSlugs:
    def test_too_with_kazakh_cyrillic_and_quotes(self):
        slug = make_slug('ТОО «Құрылыс Жиһаз»', "Алматы", unique_id=1)
        assert slug != "company"
        assert slug.endswith("-1")
        assert all(c.islower() or c.isdigit() or c == "-" for c in slug)
        assert "«" not in slug and "»" not in slug

    def test_ip_with_hyphen_in_name(self):
        # The hyphen is part of the company's own name, not just the
        # city-name separator -- must not collapse into a malformed or
        # doubled-hyphen slug.
        slug = make_slug("ИП Дерево-Мастер", "Алматы", unique_id=2)
        assert slug != "company"
        assert "--" not in slug
        assert not slug.startswith("-")
        assert slug.endswith("-2")

    def test_identical_company_names_same_city_get_different_slugs(self):
        slug_a = make_slug("Мебель Сити", "Алматы", unique_id=10)
        slug_b = make_slug("Мебель Сити", "Алматы", unique_id=11)
        assert slug_a != slug_b
        assert slug_a.endswith("-10")
        assert slug_b.endswith("-11")

    def test_empty_city_still_produces_valid_slug(self):
        slug = make_slug("Мебель Сити", "", unique_id=3)
        assert slug != "company"
        assert len(slug) >= 3
        assert slug.endswith("-3")

    def test_long_company_name_is_capped(self):
        # Regression: used to produce a 300+ char slug with no length
        # limit, exceeding most filesystems' ~255-byte path-component cap.
        slug = make_slug("А" * 300, "Алматы", unique_id=4)
        assert len(slug) <= 100
        assert slug.endswith("-4")

    def test_quotation_marks_and_punctuation_stripped(self):
        slug = make_slug('ТОО "Мебель & Ко."', "Алматы", unique_id=5)
        for ch in ['"', "&", ".", "«", "»"]:
            assert ch not in slug

    def test_kazakh_specific_letters_transliterated(self):
        # ә ғ қ ң ө ұ ү һ і are not in the Russian alphabet.
        slug = make_slug("Қазақстан Өнер Ұста", "Алматы", unique_id=6)
        assert slug != "company"
        assert all(c.islower() or c.isdigit() or c == "-" for c in slug)


class TestKazakhstanPhoneFormats:
    @pytest.mark.parametrize(
        "raw",
        ["8 707 123 45 67", "+7 707 123 45 67", "77071234567"],
    )
    def test_valid_formats_normalize_to_same_e164(self, raw):
        assert PhoneNumberService.normalize(raw) == "+77071234567"

    @pytest.mark.parametrize("bad", ["", None, "123", "abc", "0000000000000"])
    def test_invalid_or_empty_phone_rejected(self, bad):
        with pytest.raises(PhoneNumberError):
            PhoneNumberService.normalize(bad)

    def test_duplicate_phone_different_company_name_both_normalize_same(self):
        # Same phone, slightly different company name -- normalization
        # must be deterministic regardless of the company name attached.
        a = PhoneNumberService.normalize("+7 707 999 88 77")
        b = PhoneNumberService.normalize("8 707 999 88 77")
        assert a == b == "+77079998877"


class TestEnrichLeadWithRealisticData:
    def test_invalid_phone_produces_no_whatsapp_link_not_a_broken_one(self):
        # Regression: used to produce "https://wa.me/" (or
        # "https://wa.me/123") instead of failing safely.
        lead = Lead(id=101, name="Тест Мебель", city="Алматы", phone="abc")
        result = enrich_lead(lead)
        assert result["whatsapp_url"] is None
        assert result["phone"] is None

    def test_garbage_digit_phone_produces_no_whatsapp_link(self):
        lead = Lead(id=102, name="Тест Мебель", city="Алматы", phone="123")
        result = enrich_lead(lead)
        assert result["whatsapp_url"] is None

    def test_valid_phone_produces_safe_whatsapp_link(self):
        lead = Lead(id=103, name="Тест Мебель", city="Алматы", phone="8 707 123 45 67")
        result = enrich_lead(lead)
        assert result["whatsapp_url"] == "https://wa.me/77071234567"
        assert result["phone"] == "+77071234567"

    def test_empty_city_lead_enriches_successfully(self):
        lead = Lead(id=104, name="Мебель Сити", city="", phone="+77001112233")
        result = enrich_lead(lead)
        assert result["slug"]
        assert result["slug"] != "company"

    def test_kazakh_cyrillic_company_enriches_successfully(self):
        lead = Lead(id=105, name='ТОО «Құрылыс Жиһаз»', city="Алматы", phone="+77001112233")
        result = enrich_lead(lead)
        assert result["slug"] != "company"
        assert result["whatsapp_url"] == "https://wa.me/77001112233"

    def test_normalize_phone_matches_phone_number_service(self):
        # Guards against the two implementations drifting apart again.
        for raw in ["8 707 123 45 67", "+7 707 123 45 67", "77071234567"]:
            assert normalize_phone(raw) == PhoneNumberService.normalize(raw)

    def test_make_whatsapp_url_none_for_all_invalid_inputs(self):
        for bad in ["", None, "abc", "123"]:
            assert make_whatsapp_url(bad) is None
