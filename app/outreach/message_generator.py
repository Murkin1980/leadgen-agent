from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

OPT_OUT_TEXT_RU = "Если вы не хотите получать сообщения, ответьте «стоп»."
OPT_OUT_TEXT_KK = "Хабар алғыңыз келмесе, «тоқтату» деп жауап беріңіз."


@dataclass
class GeneratedMessages:
    first_contact: str
    follow_up: str
    whatsapp_short: str
    email_subject: str
    email_body: str
    telegram_body: str
    language: str = "ru"


@dataclass
class MessageContext:
    company_name: str
    city: str
    category: str = ""
    preview_url: str = ""
    phone: str = ""
    language: str = "ru"
    follow_up_number: int = 0


def _load_template(name: str) -> str:
    import importlib.resources
    try:
        import app.outreach.templates as tmpl_pkg
        ref = importlib.resources.files(tmpl_pkg) / f"{name}.txt"
        return ref.read_text(encoding="utf-8")
    except Exception:
        return ""


def generate_messages(ctx: MessageContext) -> GeneratedMessages:
    lang = ctx.language or "ru"
    if lang == "kk":
        return _generate_kk(ctx)
    return _generate_ru(ctx)


def _generate_ru(ctx: MessageContext) -> GeneratedMessages:
    name = ctx.company_name or "Ваша компания"
    city = ctx.city or ""
    cat = ctx.category or ""
    preview = ctx.preview_url or ""

    first_contact = (
        f"Здравствуйте! Мы нашли «{name}» в каталоге"
        + (f" ({city})" if city else "")
        + (f" по направлению «{cat}»." if cat else "")
    )
    if preview:
        first_contact += f" Мы подготовили страницу для вашего бизнеса: {preview}"
    else:
        first_contact += " Мы можем создать промо-страницу для вашего бизнеса."
    first_contact += f" {OPT_OUT_TEXT_RU}"

    follow_up = (
        f"Здравствуйте, «{name}»! "
        + ("Напоминаем про промо-страницу." if not preview else f"Вы посмотрели промо-страницу? {preview}")
        + f" {OPT_OUT_TEXT_RU}"
    )

    whatsapp_short = (
        f"Здравствуйте! «{name}»" + (f" ({city})" if city else "")
        + f" — мы подготовили промо-страницу для вас."
        + (f" {preview}" if preview else "")
        + f" {OPT_OUT_TEXT_RU}"
    )

    email_subject = f"Промо-страница для «{name}»"
    email_body = (
        f"Здравствуйте!\n\n"
        f"Мы подготовили промо-страницу для «{name}»"
        + (f" ({city})" if city else "")
        + (f" по направлению «{cat}»." if cat else ".")
        + "\n\n"
        + (f"Посмотреть: {preview}\n\n" if preview else "")
        + "Если у вас есть вопросы, ответьте на это письмо.\n\n"
        f"{OPT_OUT_TEXT_RU}"
    )

    telegram_body = (
        f"Здравствуйте! «{name}» — подготовлена промо-страница."
        + (f" {preview}" if preview else "")
        + f" {OPT_OUT_TEXT_RU}"
    )

    return GeneratedMessages(
        first_contact=first_contact,
        follow_up=follow_up,
        whatsapp_short=whatsapp_short,
        email_subject=email_subject,
        email_body=email_body,
        telegram_body=telegram_body,
        language="ru",
    )


def _generate_kk(ctx: MessageContext) -> GeneratedMessages:
    name = ctx.company_name or "Сіздің компания"
    city = ctx.city or ""
    cat = ctx.category or ""
    preview = ctx.preview_url or ""

    first_contact = (
        f"Сәлеметсіз бе! Біз «{name}» каталогынан таптық"
        + (f" ({city})" if city else "")
        + (f" «{cat}» бағыты бойынша." if cat else "")
    )
    if preview:
        first_contact += f" Біз сіздің бизнес үшін бет дайындадық: {preview}"
    else:
        first_contact += " Біз сіздің бизнес үшін жарнама бетін жасай аламыз."
    first_contact += f" {OPT_OUT_TEXT_KK}"

    follow_up = (
        f"Сәлеметсіз бе, «{name}»! "
        + ("Жарнама беті туралы еске саламыз." if not preview else f"Сіз жарнама бетін қарастырдыңыз ба? {preview}")
        + f" {OPT_OUT_TEXT_KK}"
    )

    whatsapp_short = (
        f"Сәлеметсіз бе! «{name}»" + (f" ({city})" if city else "")
        + f" — біз сіз үшін жарнама беті дайындадық."
        + (f" {preview}" if preview else "")
        + f" {OPT_OUT_TEXT_KK}"
    )

    email_subject = f"«{name}» үшін жарнама беті"
    email_body = (
        f"Сәлеметсіз бе!\n\n"
        f"Біз «{name}» үшін жарнама бетін дайындадық"
        + (f" ({city})" if city else "")
        + (f" «{cat}» бағыты бойынша." if cat else ".")
        + "\n\n"
        + (f"Қарау: {preview}\n\n" if preview else "")
        + "Сұрақтарыңыз болса, осы хатқа жауап беріңіз.\n\n"
        f"{OPT_OUT_TEXT_KK}"
    )

    telegram_body = (
        f"Сәлеметсіз бе! «{name}» — жарнама беті дайын."
        + (f" {preview}" if preview else "")
        + f" {OPT_OUT_TEXT_KK}"
    )

    return GeneratedMessages(
        first_contact=first_contact,
        follow_up=follow_up,
        whatsapp_short=whatsapp_short,
        email_subject=email_subject,
        email_body=email_body,
        telegram_body=telegram_body,
        language="kk",
    )
