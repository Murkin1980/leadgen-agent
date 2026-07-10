from __future__ import annotations

from app.enrichment.enricher import enrich_lead
from app.models.lead import Lead


class TemplateTextGenerationAdapter:
    def generate_profile(self, lead: Lead) -> dict:
        enriched = enrich_lead(lead)

        meta_title = f"{enriched['specialization']} — {enriched['company_name']}"
        meta_description = f"{enriched['specialization']}. {', '.join(enriched['services'][:3])}."

        return {
            "meta": {
                "title": meta_title,
                "description": meta_description,
            },
            "company": {
                "name": enriched["company_name"],
                "city": enriched["city"],
                "phone": enriched["phone"],
                "whatsapp_url": enriched["whatsapp_url"],
            },
            "hero": {
                "title": f"{enriched['specialization'].rstrip()} в {enriched['city']}",
                "subtitle": f"{enriched['company_name']} — изготовим мебель по индивидуальным размерам",
                "cta_text": enriched["cta"],
            },
            "services": [
                {"title": s, "description": f"Профессиональное изготовление: {s.lower()}"}
                for s in enriched["services"]
            ],
            "advantages": enriched["advantages"],
            "contacts": {
                "phone": enriched["phone"],
                "whatsapp_url": enriched["whatsapp_url"],
                "address": lead.address or "",
                "city": enriched["city"],
            },
            "theme": {
                "style": "modern",
                "primary_color": "#1f2937",
                "accent_color": "#c9975b",
            },
        }
