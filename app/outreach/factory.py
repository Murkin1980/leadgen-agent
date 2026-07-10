from app.config import settings
from app.outreach.provider import OutreachProvider
from app.outreach.mock_provider import MockOutreachProvider
from app.outreach.email_provider import EmailOutreachProvider
from app.outreach.whatsapp_provider import WhatsAppCloudProvider
from app.outreach.telegram_provider import TelegramOutreachProvider


def create_outreach_provider(provider: str | None = None) -> OutreachProvider:
    provider = provider or settings.outreach_provider
    providers = {
        "mock": MockOutreachProvider,
        "email": EmailOutreachProvider,
        "whatsapp": WhatsAppCloudProvider,
        "telegram": TelegramOutreachProvider,
    }
    cls = providers.get(provider)
    if not cls:
        raise ValueError(f"Unknown outreach provider: {provider}")
    return cls()


def get_available_outreach_providers() -> list[str]:
    return ["mock", "email", "whatsapp", "telegram"]
