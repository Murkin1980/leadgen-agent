from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class CollectedCompany(BaseModel):
    source_id: str
    name: str
    category: str
    city: str
    address: str
    phone: str | None = None
    website: str | None = None
    instagram: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    source_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class CollectedPage:
    items: list[CollectedCompany]
    page: int
    page_size: int
    has_more: bool
    provider_metadata: dict[str, Any] = field(default_factory=dict)
