from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import settings
from app.collector.exceptions import CollectorConfigError

if TYPE_CHECKING:
    from app.collector.adapter import CollectorAdapter

logger = logging.getLogger(__name__)


def create_collector(provider: str | None = None) -> CollectorAdapter:
    """Factory function to create collector adapter based on provider."""
    provider = provider or settings.collector_provider

    if provider == "mock":
        from app.collector.mock import MockCollectorAdapter
        logger.info("Creating MockCollectorAdapter")
        return MockCollectorAdapter()

    elif provider == "two_gis":
        from app.collector.adapters.two_gis import TwoGisCollectorAdapter
        logger.info("Creating TwoGisCollectorAdapter")
        return TwoGisCollectorAdapter(
            api_key=settings.two_gis_api_key,
            api_url=settings.two_gis_api_url,
            city_id=settings.two_gis_city_id,
            max_retries=settings.two_gis_max_retries,
            retry_delay=settings.two_gis_retry_delay,
        )

    elif provider == "csv":
        from app.collector.adapters.csv import CsvCollectorAdapter
        logger.info("Creating CsvCollectorAdapter")
        return CsvCollectorAdapter(
            file_path=settings.csv_file_path,
            page_size=settings.csv_page_size,
        )

    else:
        raise CollectorConfigError(
            f"Unknown collector provider: {provider}. "
            f"Supported providers: mock, two_gis, csv"
        )


def get_available_providers() -> list[str]:
    """Return list of available collector providers."""
    providers = ["mock", "csv"]
    if settings.two_gis_api_key:
        providers.append("two_gis")
    return providers


def validate_provider(provider: str) -> bool:
    """Check if provider is available and configured."""
    available = get_available_providers()
    return provider in available
