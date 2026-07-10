from __future__ import annotations

import json

from app.generation.base import GeneratedProfile, GeneratedProfileClaim
from app.generation.context import GenerationContext


class MockTextGenerationAdapter:
    def __init__(self, deterministic: bool = True):
        self.deterministic = deterministic
        self.call_count = 0

    def generate(self, context: GenerationContext) -> GeneratedProfile:
        self.call_count += 1
        lang = context.language or "ru"

        if lang == "kk":
            hero_title = f"{context.category} — {context.city}"
            hero_subtitle = f"{context.company_name} — жеке өлшемдер бойынша жиһаз өндіру"
            cta = "Бағаны есептеу"
        else:
            hero_title = f"{context.category} в {context.city}"
            hero_subtitle = f"{context.company_name} — изготовим мебель по индивидуальным размерам"
            cta = "Рассчитать стоимость"

        phone = context.phone or ""
        whatsapp_url = context.whatsapp_url or ""
        services = context.services or ["Услуга 1", "Услуга 2"] if lang == "ru" else ["Қызмет 1", "Қызмет 2"]

        claims = [
            GeneratedProfileClaim(text=context.company_name, source_field="company_name", verified=True),
            GeneratedProfileClaim(text=f"Город: {context.city}", source_field="city", verified=True),
        ]
        if phone:
            claims.append(GeneratedProfileClaim(text=f"Телефон: {phone}", source_field="phone", verified=True))

        meta_title = f"{context.category} — {context.company_name}" if lang == "ru" else f"{context.category} — {context.company_name}"
        meta_description = f"{context.category}. {', '.join(services[:3])}."

        profile_data = {
            "meta": {"title": meta_title, "description": meta_description},
            "company": {
                "name": context.company_name,
                "city": context.city,
                "phone": phone,
                "whatsapp_url": whatsapp_url,
            },
            "hero": {
                "title": hero_title,
                "subtitle": hero_subtitle,
                "cta_text": cta,
            },
            "services": [
                {"title": s, "description": f"Профессиональное изготовление: {s.lower()}" if lang == "ru" else f"Кәсіби өндіріс: {s.lower()}"}
                for s in services
            ],
            "advantages": ["Преимущество 1", "Преимущество 2"] if lang == "ru" else ["Артықшылық 1", "Артықшылық 2"],
            "work_stages": [
                {"number": 1, "title": "Замер", "description": "Выезд специалиста"},
                {"number": 2, "title": "Проект", "description": "Разработка дизайн-проекта"},
            ],
            "faq": [
                {"question": "Сроки?", "answer": "От 7 дней."},
                {"question": "Гарантия?", "answer": "Есть."},
            ],
            "contacts": {
                "phone": phone,
                "whatsapp_url": whatsapp_url,
                "address": context.address or "",
                "city": context.city,
            },
            "theme": {
                "style": "modern",
                "primary_color": "#1f2937",
                "accent_color": "#c9975b",
            },
            "language": lang,
        }

        return GeneratedProfile(data=profile_data, claims=claims)
