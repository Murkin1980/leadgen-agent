from __future__ import annotations

from app.collector.base import CollectedCompany, CollectedPage


class TwoGisCollectorAdapter:
    """Placeholder for real 2GIS collector. Not implemented yet."""

    def search(self, city: str, category: str, limit: int) -> list[CollectedCompany]:
        raise NotImplementedError(
            "TwoGisCollectorAdapter is not implemented. "
            "Configure COLLECTOR_PROVIDER=two_gis and provide API credentials."
        )

    def search_page(
        self,
        city: str,
        category: str,
        page: int = 1,
        page_size: int = 20,
    ) -> CollectedPage:
        raise NotImplementedError(
            "TwoGisCollectorAdapter is not implemented. "
            "Configure COLLECTOR_PROVIDER=two_gis and provide API credentials."
        )
