import pytest
from app.collector.mock import MockCollectorAdapter
from app.models.lead import Lead
from app.enrichment.enricher import enrich_lead


class TestFilteringLogic:
    def test_no_website_companies_eligible(self):
        adapter = MockCollectorAdapter()
        companies = adapter.search(city="Алматы", category="мебель на заказ", limit=100)
        eligible = [c for c in companies if not c.website and c.phone and c.name.strip()]
        assert len(eligible) > 0

    def test_with_website_companies_excluded(self):
        adapter = MockCollectorAdapter()
        companies = adapter.search(city="Алматы", category="мебель на заказ", limit=100)
        with_website = [c for c in companies if c.website]
        assert len(with_website) > 0
        for c in with_website:
            assert c.website.startswith("http")

    def test_all_companies_have_source_id(self):
        adapter = MockCollectorAdapter()
        companies = adapter.search(city="Алматы", category="мебель на заказ", limit=100)
        source_ids = set()
        for c in companies:
            assert c.source_id
            assert c.source_id not in source_ids
            source_ids.add(c.source_id)

    def test_enrichment_produces_valid_slug(self):
        lead = Lead(name="Mebel Art", city="Алматы", category="Мебель на заказ", phone="+77001112233")
        result = enrich_lead(lead)
        assert result["slug"]
        assert len(result["slug"]) > 2
        assert " " not in result["slug"]
