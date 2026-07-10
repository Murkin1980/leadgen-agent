import logging
from typing import Any

from app.config import settings
from app.outreach.provider import DeliveryStatus, OutreachProvider, SendResult

logger = logging.getLogger(__name__)


class TelegramOutreachProvider(OutreachProvider):
    def __init__(self):
        self._enabled = bool(settings.telegram_bot_token)
        if not self._enabled:
            logger.warning("TelegramOutreachProvider disabled: missing bot token")

    def send(self, recipient: str, body: str, subject: str | None = None, **kwargs: Any) -> SendResult:
        if not self._enabled:
            return SendResult(success=False, error_code="not_configured", error_message="Telegram not configured")
        raise NotImplementedError("Real Telegram sending not implemented in MVP")

    def get_status(self, provider_message_id: str) -> DeliveryStatus:
        return DeliveryStatus.unknown
