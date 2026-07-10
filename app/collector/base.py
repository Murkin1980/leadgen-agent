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
    raw_payload: dict[str, Any] | None = None


@dataclass
class CollectedPage:
    items: list[CollectedCompany]
    page: int
    page_size: int
    has_more: bool
    total: int | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.total is None:
            self.total = len(self.items)
