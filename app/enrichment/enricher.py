from __future__ import annotations

import re
import unicodedata

from app.models.lead import Lead

SERVICES_MAP: dict[str, list[str]] = {
    "мебель": [
        "Кухни на заказ",
        "Шкафы и гардеробные",
        "Мебель для спальни",
        "Мебель для гостиной",
    ],
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

ADVANTAGES = [
    "Индивидуальное изготовление",
    "Выезд замерщика",
    "Подбор материалов",
    "Доставка и монтаж",
    "Гарантия на изделие",
]

CTA_OPTIONS = [
    "Рассчитать стоимость",
    "Заказать замер",
    "Получить консультацию",
    "Заказать проект",
]

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("7") and len(digits) == 11:
        return f"+{digits}"
    if digits.startswith("8") and len(digits) == 11:
        return f"+7{digits[1:]}"
    if len(digits) == 10:
        return f"+7{digits}"
    return phone


def make_whatsapp_url(phone: str | None) -> str | None:
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    digits = re.sub(r"\D", "", normalized)
    return f"https://wa.me/{digits}"


def make_slug(name: str, city: str) -> str:
    raw = f"{city}-{name}".lower()
    raw = unicodedata.normalize("NFKD", raw)
    raw = re.sub(r"[^a-z0-9а-яё\s-]", "", raw)
    raw = re.sub(r"[\s]+", "-", raw.strip())
    raw = re.sub(r"-+", "-", raw)
    raw = raw.strip("-")
    if len(raw) < 3:
        raw = f"company-{raw}" if raw else "company"
    if not SLUG_RE.match(raw):
        raw = re.sub(r"[^a-z0-9-]", "", raw)
        raw = re.sub(r"-+", "-", raw).strip("-")
        if len(raw) < 3:
            raw = f"company-{raw}" if raw else "company"
    return raw


def classify_specialization(name: str, category: str) -> str:
    combined = f"{name} {category}".lower()
    for keyword, spec in [
        ("кухн", "Изготовление кухонь на заказ"),
        ("офис", "Производство офисной мебели"),
        ("гардероб", "Производство гардеробных и систем хранения"),
        ("шкаф", "Изготовление шкафов и систем хранения"),
        ("дерев", "Производство мебели из натурального дерева"),
    ]:
        if keyword in combined:
            return spec
    return "Изготовление мебели на заказ"


def build_services(name: str, category: str) -> list[str]:
    combined = f"{name} {category}".lower()
    for keyword, services in SERVICES_MAP.items():
        if keyword in combined:
            return services
    return SERVICES_MAP["мебель"]


def select_cta(city: str) -> str:
    return f"{CTA_OPTIONS[0]} в {city}"


def enrich_lead(lead: Lead) -> dict:
    slug = make_slug(lead.name, lead.city or "")
    specialization = classify_specialization(lead.name, lead.category or "")
    services = build_services(lead.name, lead.category or "")
    phone = normalize_phone(lead.phone)
    whatsapp_url = make_whatsapp_url(lead.phone)
    cta = select_cta(lead.city or "")

    return {
        "company_name": lead.name.strip(),
        "city": lead.city or "",
        "specialization": specialization,
        "services": services,
        "advantages": ADVANTAGES,
        "phone": phone,
        "whatsapp_url": whatsapp_url,
        "slug": slug,
        "cta": cta,
    }
