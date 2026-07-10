from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GenerationContext:
    company_name: str
    city: str
    category: str
    phone: str | None = None
    whatsapp_url: str | None = None
    verified_phone: str | None = None
    social_links: list[str] = field(default_factory=list)
    rating: float | None = None
    reviews_count: int | None = None
    address: str | None = None
    services: list[str] = field(default_factory=list)
    qualification_reasons: list[str] = field(default_factory=list)
    source_metadata: dict[str, str | None] = field(default_factory=dict)
    language: str = "ru"
    notes: str | None = None

    @classmethod
    def from_lead(cls, lead, qualification_reasons: list[str] | None = None) -> "GenerationContext":
        social_links = []
        if lead.instagram:
            social_links.append(lead.instagram)
        if lead.telegram:
            social_links.append(lead.telegram)

        return cls(
            company_name=lead.name.strip() if lead.name else "",
            city=lead.city or "",
            category=lead.category or "",
            phone=lead.phone,
            whatsapp_url=lead.whatsapp,
            verified_phone=lead.phone,
            social_links=social_links,
            rating=lead.rating,
            reviews_count=lead.reviews_count,
            address=lead.address,
            qualification_reasons=qualification_reasons or [],
            source_metadata={
                "source": lead.source,
                "source_id": lead.source_id,
                "source_url": lead.source_url,
            },
        )
