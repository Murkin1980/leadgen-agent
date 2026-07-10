import uuid

import pytest
from app.collector.mock import MockCollectorAdapter
from app.collector.base import CollectedPage


class TestMockCollectorPagination:
    def test_search_page_returns_page(self):
        adapter = MockCollectorAdapter()
        page = adapter.search_page("Алматы", "мебель", page=1, page_size=3)
        assert isinstance(page, CollectedPage)
        assert page.page == 1
        assert page.page_size == 3
        assert len(page.items) == 3

    def test_search_page_second_page(self):
        adapter = MockCollectorAdapter()
        page = adapter.search_page("Алматы", "мебель", page=2, page_size=3)
        assert page.page == 2
        assert len(page.items) == 3

    def test_search_page_has_more(self):
        adapter = MockCollectorAdapter()
        page1 = adapter.search_page("Алматы", "мебель", page=1, page_size=3)
        assert page1.has_more is True

        page2 = adapter.search_page("Алматы", "мебель", page=2, page_size=3)
        assert page2.has_more is False

    def test_search_page_beyond_data(self):
        adapter = MockCollectorAdapter()
        page = adapter.search_page("Алматы", "мебель", page=100, page_size=3)
        assert len(page.items) == 0
        assert page.has_more is False

    def test_search_page_provider_metadata(self):
        adapter = MockCollectorAdapter()
        page = adapter.search_page("Алматы", "мебель", page=1, page_size=6)
        assert "total" in page.provider_metadata
        assert page.provider_metadata["total"] == 6

    def test_search_delegates_to_search_page(self):
        adapter = MockCollectorAdapter()
        results = adapter.search("Алматы", "мебель", 3)
        assert len(results) == 3

    def test_all_items_have_source_id(self):
        adapter = MockCollectorAdapter()
        page = adapter.search_page("Алматы", "мебель", page=1, page_size=100)
        for item in page.items:
            assert item.source_id
            assert item.source_id.startswith("mock_")


class TestCollectorProviderSelection:
    def test_mock_provider_returns_mock(self):
        from app.config import settings
        original = settings.collector_provider
        try:
            settings.collector_provider = "mock"
            from app.workers.collector_worker import _get_collector
            collector = _get_collector()
            assert isinstance(collector, MockCollectorAdapter)
        finally:
            settings.collector_provider = original

    def test_two_gis_provider_returns_stub(self):
        from app.config import settings
        original = settings.collector_provider
        try:
            settings.collector_provider = "two_gis"
            from app.workers.collector_worker import _get_collector
            from app.collector.adapters.two_gis import TwoGisCollectorAdapter
            collector = _get_collector()
            assert isinstance(collector, TwoGisCollectorAdapter)
        finally:
            settings.collector_provider = original
