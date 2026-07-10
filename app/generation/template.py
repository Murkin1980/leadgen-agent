from __future__ import annotations

from app.enrichment.enricher import (
    classify_specialization,
    make_whatsapp_url,
    normalize_phone,
)
from app.generation.base import GeneratedProfile, GeneratedProfileClaim
from app.generation.context import GenerationContext

CTA_RU = "Рассчитать стоимость"
CTA_KK = "Бағаны есептеу"

SERVICES_MAP: dict[str, list[str]] = {
    "кухн": [
        "Кухни на заказ",
        "Кухонные фасады",
        "Столешницы",
        "Фурнитура",
    ],
    "офис": [
        "Офисные столы",
        "Шкафы для документов",
        "Стеллажи",
        "Перегородки",
    ],
    "шкаф": [
        "Шкафы-купе",
        "Гардеробные",
        "Системы хранения",
        "Стеллажи",
    ],
    "дерев": [
        "Мебель из массива",
        "Кухни из дерева",
        "Столы и стулья",
        "Декоративные элементы",
    ],
}

SERVICES_MAP_KK: dict[str, list[str]] = {
    "кухн": [
        "Тапсырыс бойынша ас үйлер",
        "Ас үй фасадтары",
        "Үстел үсті",
        "Фурнитура",
    ],
    "офис": [
        "Кеңсе үстелдері",
        "Құжаттар шкафы",
        "Сөрелер",
        "Бөлу қабырғалары",
    ],
    "шкаф": [
        "Киім шкафтары",
        "Киім бөлмелері",
        "Сақтау жүйелері",
        "Сөрелер",
    ],
    "дерев": [
        "Ағаштан жасалған жиһаз",
        "Ағаш ас үйлер",
        "Үстелдер мен орындықтар",
        "Әшекейлік элементтер",
    ],
}

ADVANTAGES_RU = [
    "Индивидуальное изготовление",
    "Выезд замерщика",
    "Подбор материалов",
    "Доставка и монтаж",
    "Гарантия на изделие",
]

ADVANTAGES_KK = [
    "Жеке өндіріс",
    "Өлшеушінің шығуы",
    "Материалдарды таңдау",
    "Жеткізу және орнату",
    "Өнімге кепілдік",
]

FAQS_RU = [
    {"question": "Сколько времени занимает изготовление?", "answer": "Срок изготовления зависит от сложности проекта и составляет от 7 до 21 рабочего дня."},
    {"question": "Как происходит замер?", "answer": "Наш специалист выезжает на объект, делает точные замеры и согласовывает детали."},
    {"question": "Предоставляете ли вы гарантию?", "answer": "Да, мы предоставляем гарантию на все изделия."},
    {"question": "Можно ли посмотреть примеры работ?", "answer": "Да, мы предоставляем фото выполненных проектов."},
]

FAQS_KK = [
    {"question": "Өндіріс қанша уақыт алады?", "answer": "Өндіріс мерзімі жобаның күрделілігіне байланысты және 7-ден 21 жұмыс күніне дейін."},
    {"question": "Өлшеу қалай жүреді?", "answer": "Біздің маман нысанға шығып, дәл өлшеу жасайды және мәселелерді келіседі."},
    {"question": "Кепілдік бересіз бе?", "answer": "Иә, біз барлық өнімдерге кепілдік береміз."},
    {"question": "Жұмыс үлгілерін көруге бола ма?", "answer": "Иә, біз орындалған жобалардың фотоларын береміз."},
]


FALLBACK_SERVICES_RU = [
    "Кухни на заказ",
    "Шкафы и гардеробные",
    "Мебель для спальни",
    "Мебель для гостиной",
]

FALLBACK_SERVICES_KK = [
    "Тапсырыс бойынша ас үйлер",
    "Киім шкафтары",
    "Жатын бөлме жиһазы",
    "Қонақ бөлме жиһазы",
]


def _get_services(category: str, language: str) -> list[str]:
    combined = (category or "").lower()
    services_map = SERVICES_MAP_KK if language == "kk" else SERVICES_MAP
    default_map = FALLBACK_SERVICES_KK if language == "kk" else FALLBACK_SERVICES_RU
    for keyword, services in services_map.items():
        if keyword in combined:
            return services
    return default_map


class TemplateTextGenerationAdapter:
    def generate(self, context: GenerationContext) -> GeneratedProfile:
        lang = context.language or "ru"
        specialization = classify_specialization(context.company_name, context.category)
        phone = normalize_phone(context.phone) or context.phone or ""
        whatsapp_url = context.whatsapp_url or (make_whatsapp_url(phone) if phone else "")
        cta = CTA_KK if lang == "kk" else CTA_RU
        city_label = context.city or ""

        if lang == "kk":
            hero_title = f"{specialization} — {city_label}"
            hero_subtitle = f"{context.company_name} — жеке өлшемдер бойынша жиһаз өндіру"
            services = _get_services(context.category, "kk")
            advantages = ADVANTAGES_KK
            faqs = FAQS_KK
            meta_title = f"{specialization} — {context.company_name}"
            meta_description = f"{specialization}. {', '.join(services[:3])}."
        else:
            hero_title = f"{specialization.rstrip()} в {city_label}"
            hero_subtitle = f"{context.company_name} — изготовим мебель по индивидуальным размерам"
            services = _get_services(context.category, "ru")
            advantages = ADVANTAGES_RU
            faqs = FAQS_RU
            meta_title = f"{specialization} — {context.company_name}"
            meta_description = f"{specialization}. {', '.join(services[:3])}."

        if context.services:
            services = context.services

        claims = [
            GeneratedProfileClaim(text=meta_title, source_field="company_name", verified=True),
            GeneratedProfileClaim(text=f"Город: {city_label}", source_field="city", verified=True),
        ]
        if phone:
            claims.append(GeneratedProfileClaim(text=f"Телефон: {phone}", source_field="phone", verified=True))
        if context.rating is not None:
            claims.append(GeneratedProfileClaim(
                text=f"Рейтинг: {context.rating}",
                source_field="rating",
                verified=True,
            ))
        if context.reviews_count is not None:
            claims.append(GeneratedProfileClaim(
                text=f"Отзывов: {context.reviews_count}",
                source_field="reviews_count",
                verified=True,
            ))

        profile_data = {
            "meta": {"title": meta_title, "description": meta_description},
            "company": {
                "name": context.company_name,
                "city": city_label,
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
            "advantages": advantages,
            "work_stages": [
                {"number": i + 1, "title": step[0], "description": step[1]}
                for i, step in enumerate([
                    ("Замер", "Выезд специалиста на объект"),
                    ("Проект", "Разработка дизайн-проекта"),
                    ("Производство", "Изготовление мебели в мастерской"),
                    ("Монтаж", "Доставка и установка на объекте"),
                ] if lang == "ru" else [
                    ("Өлшеу", "Маманның нысанға шығуы"),
                    ("Жоба", "Дизайн-жобаны әзірлеу"),
                    ("Өндіріс", "Мастерханада жиһаз өндіру"),
                    ("Орнату", "Жеткізу және нысанда орнату"),
                ])
            ],
            "faq": faqs,
            "contacts": {
                "phone": phone,
                "whatsapp_url": whatsapp_url,
                "address": context.address or "",
                "city": city_label,
            },
            "theme": {
                "style": "modern",
                "primary_color": "#1f2937",
                "accent_color": "#c9975b",
            },
            "language": lang,
        }

        return GeneratedProfile(data=profile_data, claims=claims)
