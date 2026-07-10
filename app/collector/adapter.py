from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.collector.base import CollectedCompany, CollectedPage


class CollectorAdapter(Protocol):
    def search(
        self,
        city: str,
        category: str,
        limit: int,
    ) -> list[CollectedCompany]: ...

    def search_page(
        self,
        city: str,
        category: str,
        page: int,
        page_size: int,
    ) -> CollectedPage: ...
