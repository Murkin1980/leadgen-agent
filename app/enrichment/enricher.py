from __future__ import annotations

import re
import unicodedata

from app.models.lead import Lead
from app.outreach.phone import PhoneNumberError, PhoneNumberService

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

# Cyrillic -> Latin transliteration (Russian alphabet plus the extra Kazakh
# Cyrillic letters). Without this, slugs for Cyrillic company names/cities
# (the vast majority of leads this product targets) collapse to the
# "company" fallback, and every lead's landing page overwrites the same
# sites/public/company/ directory.
CYRILLIC_TO_LATIN: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # Extra Kazakh Cyrillic letters
    "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u",
    "һ": "h", "і": "i",
}


def transliterate(text: str) -> str:
    return "".join(CYRILLIC_TO_LATIN.get(ch, ch) for ch in text)


def normalize_phone(phone: str | None) -> str | None:
    """Normalize to E.164, or None if the number isn't a valid KZ number.

    Delegates to PhoneNumberService (the same validated normalizer used
    for outreach) instead of a separate, looser implementation. The old
    version fell through to returning the raw input unchanged for
    anything that didn't match its three patterns -- e.g.
    normalize_phone("abc") returned "abc" -- which then flowed into
    make_whatsapp_url() as a broken "https://wa.me/" link (or worse,
    "https://wa.me/123" for garbage digit strings) and into the landing
    page's displayed phone number.
    """
    try:
        return PhoneNumberService.normalize(phone)
    except PhoneNumberError:
        return None


def make_whatsapp_url(phone: str | None) -> str | None:
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    digits = re.sub(r"\D", "", normalized)
    return f"https://wa.me/{digits}"


def make_slug(name: str, city: str, unique_id: int | str | None = None) -> str:
    raw = f"{city}-{name}".lower()
    raw = transliterate(raw)
    raw = unicodedata.normalize("NFKD", raw)
    raw = raw.encode("ascii", "ignore").decode("ascii")
    raw = re.sub(r"[^a-z0-9\s-]", "", raw)
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

    # Cap length well under the ~255-byte filesystem path-component limit
    # (sites/drafts/{slug}/ uses the slug as a directory name directly).
    # Long legal-entity names ("Товарищество с ограниченной
    # ответственностью ...") are common enough in real data that this isn't
    # a hypothetical edge case.
    max_base_len = 80
    if len(raw) > max_base_len:
        raw = raw[:max_base_len].rstrip("-")

    # Always disambiguate with the lead's own id: two companies can share a
    # name (or both transliterate to the same base slug), and each lead's
    # landing page must live in its own sites/public/{slug}/ directory.
    if unique_id is not None:
        raw = f"{raw}-{unique_id}"
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
    slug = make_slug(lead.name, lead.city or "", unique_id=lead.id)
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
