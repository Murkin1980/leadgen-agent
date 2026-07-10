import pytest
from app.collector.mock import MockCollectorAdapter


class TestCollector:
    def test_returns_companies(self):
        adapter = MockCollectorAdapter()
        results = adapter.search(city="Алматы", category="мебель на заказ", limit=10)
        assert len(results) > 0

    def test_respects_limit(self):
        adapter = MockCollectorAdapter()
        results = adapter.search(city="Алматы", category="мебель на заказ", limit=3)
        assert len(results) == 3

    def test_filters_companies_with_website(self):
        adapter = MockCollectorAdapter()
        all_companies = adapter.search(city="Алматы", category="мебель на заказ", limit=100)
        no_website = [c for c in all_companies if not c.website]
        with_website = [c for c in all_companies if c.website]
        assert len(no_website) > 0
        assert len(with_website) > 0

    def test_all_companies_have_phone(self):
        adapter = MockCollectorAdapter()
        results = adapter.search(city="Алматы", category="мебель на заказ", limit=10)
        for company in results:
            assert company.phone is not None
            assert company.phone.startswith("+7")

    def test_all_companies_have_name(self):
        adapter = MockCollectorAdapter()
        results = adapter.search(city="Алматы", category="мебель на заказ", limit=10)
        for company in results:
            assert company.name
            assert company.name.strip()
