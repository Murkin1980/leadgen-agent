from __future__ import annotations

from app.collector.base import CollectedCompany


class TwoGisCollectorAdapter:
    """Placeholder for real 2GIS collector. Not implemented yet."""

    def search(
        self,
        city: str,
        category: str,
        limit: int,
    ) -> list[CollectedCompany]:
        raise NotImplementedError(
            "TwoGisCollectorAdapter is not implemented. "
            "Set TEXT_GENERATOR_PROVIDER=template and use MockCollectorAdapter."
        )
