from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.collector.base import CollectedCompany, CollectedPage
from app.collector.exceptions import (
    CollectorAuthError,
    CollectorConfigError,
    CollectorNetworkError,
    CollectorRateLimitError,
    CollectorValidationError,
)
from app.config import settings

logger = logging.getLogger(__name__)


class TwoGisCollectorAdapter:
    """Real 2GIS collector adapter using the Catalog API."""

    def __init__(
        self,
        api_key: str = "",
        api_url: str = "",
        city_id: str = "",
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.api_key = api_key or settings.two_gis_api_key
        self.api_url = api_url or settings.two_gis_api_url
        self.city_id = city_id or settings.two_gis_city_id
        self.max_retries = max_retries or settings.two_gis_max_retries
        self.retry_delay = retry_delay or settings.two_gis_retry_delay

        if not self.api_key:
            raise CollectorConfigError(
                "2GIS API key is required. Set TWO_GIS_API_KEY environment variable."
            )

        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": settings.verification_user_agent,
            },
        )

    def _request_with_retry(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.request(method, url, **kwargs)

                if response.status_code == 401:
                    raise CollectorAuthError("Invalid API key")

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", self.retry_delay))
                    raise CollectorRateLimitError(retry_after=retry_after)

                if response.status_code == 404:
                    raise CollectorNotFoundError(f"Resource not found: {url}")

                if response.status_code >= 400:
                    raise CollectorNetworkError(
                        f"HTTP {response.status_code}: {response.text[:200]}"
                    )

                return response

            except CollectorAuthError:
                raise
            except CollectorRateLimitError as e:
                if attempt < self.max_retries - 1:
                    wait_time = e.retry_after or self.retry_delay * (2 ** attempt)
                    logger.warning(f"Rate limited, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                raise
            except (CollectorNetworkError, httpx.RequestError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Request failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                raise

        raise CollectorNetworkError(f"Max retries exceeded: {last_error}")

    def _parse_company(self, item: dict[str, Any]) -> CollectedCompany | None:
        """Parse a single 2GIS item into a CollectedCompany."""
        try:
            name = item.get("name", "").strip()
            if not name:
                return None

            address = ""
            if item.get("address_name"):
                address = item["address_name"]
            elif item.get("full_address_name"):
                address = item["full_address_name"]

            phone = None
            if item.get("contact_groups"):
                for group in item["contact_groups"]:
                    for contact in group.get("contacts", []):
                        if contact.get("type") == "phone":
                            phone = contact.get("value")
                            break
                    if phone:
                        break

            website = None
            if item.get("contact_groups"):
                for group in item["contact_groups"]:
                    for contact in group.get("contacts", []):
                        if contact.get("type") == "website":
                            website = contact.get("value")
                            break
                    if website:
                        break

            instagram = None
            if item.get("contact_groups"):
                for group in item["contact_groups"]:
                    for contact in group.get("contacts", []):
                        if contact.get("type") == "instagram":
                            instagram = contact.get("value")
                            break
                    if instagram:
                        break

            point = item.get("point", {})
            latitude = point.get("lat")
            longitude = point.get("lon")

            rubrics = item.get("rubrics", [])
            category = rubrics[0]["name"] if rubrics else "Мебель на заказ"

            return CollectedCompany(
                source_id=str(item.get("id", "")),
                name=name,
                category=category,
                city=item.get("city_name", "Алматы"),
                address=address,
                phone=phone,
                website=website,
                instagram=instagram,
                rating=item.get("reviews", {}).get("general_rating"),
                reviews_count=item.get("reviews", {}).get("amount"),
                source_url=f"https://2gis.kz/firm/{item.get('id', '')}",
                latitude=latitude,
                longitude=longitude,
                raw_payload=item,
            )
        except Exception as e:
            logger.warning(f"Failed to parse 2GIS item: {e}")
            return None

    def search(
        self,
        *,
        city: str,
        category: str,
        limit: int,
    ) -> list[CollectedCompany]:
        """Search for companies using 2GIS API."""
        companies = []
        page = 1
        page_size = min(limit, settings.two_gis_page_size)

        while len(companies) < limit:
            result = self.search_page(
                city=city,
                category=category,
                page=page,
                page_size=page_size,
            )
            companies.extend(result.items)

            if not result.has_more or not result.items:
                break

            page += 1

        return companies[:limit]

    def search_page(
        self,
        *,
        city: str,
        category: str,
        page: int = 1,
        page_size: int = 20,
    ) -> CollectedPage:
        """Search for companies using 2GIS API with pagination."""
        params = {
            "page": page,
            "page_size": page_size,
            "q": category,
            "city_id": self.city_id,
            "fields": "items.reviews,items.contact_groups,items.point,items.rubrics",
            "type": "branch",
        }

        try:
            response = self._request_with_retry("GET", self.api_url, params=params)
            data = response.json()
        except Exception as e:
            logger.error(f"2GIS API request failed: {e}")
            raise

        if "result" not in data:
            raise CollectorValidationError(f"Invalid response format: {data}")

        items = data.get("result", {}).get("items", [])
        total = data.get("result", {}).get("total", 0)

        companies = []
        for item in items:
            company = self._parse_company(item)
            if company:
                companies.append(company)

        has_more = (page * page_size) < total

        return CollectedPage(
            items=companies,
            page=page,
            page_size=page_size,
            has_more=has_more,
            total=total,
            provider_metadata={"source": "2gis", "city_id": self.city_id},
        )

    def __del__(self):
        """Close HTTP client on cleanup."""
        if hasattr(self, "_client"):
            self._client.close()
