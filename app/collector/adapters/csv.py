from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path

from app.collector.base import CollectedCompany, CollectedPage

logger = logging.getLogger(__name__)


class CsvCollectorAdapter:
    """CSV-based collector adapter for importing companies from a CSV file."""

    def __init__(self, file_path: str = "import/companies.csv", page_size: int = 20):
        self.file_path = Path(file_path)
        self.page_size = page_size
        self._companies: list[CollectedCompany] | None = None

    def _load_companies(self) -> list[CollectedCompany]:
        if self._companies is not None:
            return self._companies

        if not self.file_path.exists():
            logger.warning(f"CSV file not found: {self.file_path}")
            self._companies = []
            return self._companies

        companies = []
        try:
            with open(self.file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        company = self._parse_row(row)
                        if company:
                            companies.append(company)
                    except Exception as e:
                        logger.warning(f"Failed to parse row: {e}")
                        continue
        except Exception as e:
            logger.error(f"Failed to read CSV file: {e}")
            self._companies = []
            return self._companies

        self._companies = companies
        logger.info(f"Loaded {len(companies)} companies from CSV")
        return self._companies

    def _parse_row(self, row: dict[str, str]) -> CollectedCompany | None:
        name = row.get("name", "").strip()
        if not name:
            return None

        source_id = row.get("source_id", "")
        if not source_id:
            source_id = hashlib.md5(f"{name}:{row.get('city', '')}".encode()).hexdigest()[:12]

        return CollectedCompany(
            source_id=source_id,
            name=name,
            category=row.get("category", "").strip() or "Мебель на заказ",
            city=row.get("city", "").strip() or "Алматы",
            address=row.get("address", "").strip() or "",
            phone=row.get("phone", "").strip() or None,
            website=row.get("website", "").strip() or None,
            instagram=row.get("instagram", "").strip() or None,
            rating=float(row.get("rating", 0) or 0) or None,
            reviews_count=int(row.get("reviews_count", 0) or 0) or None,
            source_url=row.get("source_url", "").strip() or None,
            latitude=float(row.get("latitude", 0) or 0) or None,
            longitude=float(row.get("longitude", 0) or 0) or None,
        )

    def search(
        self,
        *,
        city: str,
        category: str,
        limit: int,
    ) -> list[CollectedCompany]:
        return self.search_page(city=city, category=category, page=1, page_size=limit).items

    def search_page(
        self,
        *,
        city: str,
        category: str,
        page: int = 1,
        page_size: int = 20,
    ) -> CollectedPage:
        companies = self._load_companies()
        
        filtered = [
            c for c in companies
            if (not city or c.city.lower() == city.lower())
            and (not category or c.category.lower() == category.lower())
        ]

        start = (page - 1) * page_size
        end = start + page_size
        items = filtered[start:end]

        return CollectedPage(
            items=items,
            page=page,
            page_size=page_size,
            has_more=end < len(filtered),
            total=len(filtered),
            provider_metadata={"source": "csv", "file": str(self.file_path)},
        )
