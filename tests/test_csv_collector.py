import os
import tempfile
from pathlib import Path

import pytest
from app.collector.adapters.csv import CsvCollectorAdapter
from app.collector.base import CollectedPage


@pytest.fixture
def csv_file(tmp_path):
    """Create a temporary CSV file for testing."""
    csv_content = """source_id,name,category,city,address,phone,website,instagram,rating,reviews_count,source_url,latitude,longitude
csv_001,Test Company 1,Мебель на заказ,Алматы,ул. Тест 1,+77001112233,,@test1,4.5,50,https://example.com/1,43.24,76.94
csv_002,Test Company 2,Офисная мебель,Алматы,ул. Тест 2,+77003334455,https://test2.kz,@test2,4.2,30,https://example.com/2,43.25,76.95
csv_003,Test Company 3,Мебель на заказ,Астана,ул. Тест 3,+77005556677,,@test3,4.8,80,https://example.com/3,51.13,71.43
"""
    csv_file = tmp_path / "test_companies.csv"
    csv_file.write_text(csv_content, encoding="utf-8")
    return csv_file


@pytest.fixture
def csv_adapter(csv_file):
    """Create a CSV adapter with the test CSV file."""
    return CsvCollectorAdapter(file_path=str(csv_file), page_size=2)


class TestCsvCollector:
    def test_loads_companies(self, csv_adapter):
        companies = csv_adapter._load_companies()
        assert len(companies) == 3

    def test_parse_row_valid(self, csv_adapter):
        row = {
            "source_id": "test_001",
            "name": "Test Company",
            "category": "Мебель",
            "city": "Алматы",
            "address": "ул. Тест 1",
            "phone": "+77001112233",
            "website": "",
            "instagram": "@test",
            "rating": "4.5",
            "reviews_count": "50",
            "source_url": "https://example.com",
            "latitude": "43.24",
            "longitude": "76.94",
        }
        company = csv_adapter._parse_row(row)
        assert company is not None
        assert company.source_id == "test_001"
        assert company.name == "Test Company"
        assert company.phone == "+77001112233"
        assert company.rating == 4.5

    def test_parse_row_empty_name(self, csv_adapter):
        row = {"source_id": "test_001", "name": "", "category": "Мебель"}
        company = csv_adapter._parse_row(row)
        assert company is None

    def test_parse_row_missing_source_id(self, csv_adapter):
        row = {"name": "Test Company", "category": "Мебель", "city": "Алматы"}
        company = csv_adapter._parse_row(row)
        assert company is not None
        assert company.source_id is not None
        assert len(company.source_id) == 12

    def test_search_page_returns_page(self, csv_adapter):
        page = csv_adapter.search_page(city="Алматы", category="Мебель на заказ", page=1, page_size=2)
        assert isinstance(page, CollectedPage)
        assert page.page == 1
        assert page.page_size == 2
        assert len(page.items) <= 2

    def test_search_page_pagination(self, csv_adapter):
        page1 = csv_adapter.search_page(city="Алматы", category="", page=1, page_size=1)
        assert len(page1.items) == 1
        assert page1.has_more is True

        page2 = csv_adapter.search_page(city="Алматы", category="", page=2, page_size=1)
        assert len(page2.items) == 1
        assert page2.has_more is False

    def test_search_page_total(self, csv_adapter):
        page = csv_adapter.search_page(city="Алматы", category="", page=1, page_size=10)
        assert page.total == 2

    def test_search_page_city_filter(self, csv_adapter):
        page_almaty = csv_adapter.search_page(city="Алматы", category="", page=1, page_size=10)
        page_astana = csv_adapter.search_page(city="Астана", category="", page=1, page_size=10)
        assert len(page_almaty.items) == 2
        assert len(page_astana.items) == 1

    def test_search_page_category_filter(self, csv_adapter):
        page_furniture = csv_adapter.search_page(city="", category="Мебель на заказ", page=1, page_size=10)
        page_office = csv_adapter.search_page(city="", category="Офисная мебель", page=1, page_size=10)
        assert len(page_furniture.items) == 2
        assert len(page_office.items) == 1

    def test_search_returns_list(self, csv_adapter):
        results = csv_adapter.search(city="Алматы", category="", limit=10)
        assert len(results) == 2
        assert results[0].source_id.startswith("csv_")

    def test_search_respects_limit(self, csv_adapter):
        results = csv_adapter.search(city="Алматы", category="", limit=1)
        assert len(results) == 1

    def test_file_not_found(self, tmp_path):
        adapter = CsvCollectorAdapter(file_path=str(tmp_path / "nonexistent.csv"))
        companies = adapter._load_companies()
        assert len(companies) == 0

    def test_provider_metadata(self, csv_adapter):
        page = csv_adapter.search_page(city="Алматы", category="Мебель", page=1, page_size=10)
        assert page.provider_metadata["source"] == "csv"
        assert "file" in page.provider_metadata
