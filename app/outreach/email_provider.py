import logging
from typing import Any

from app.config import settings
from app.outreach.provider import DeliveryStatus, OutreachProvider, SendResult

logger = logging.getLogger(__name__)


class EmailOutreachProvider(OutreachProvider):
    def __init__(self):
        self._enabled = bool(settings.email_smtp_host and settings.email_from_address)
        if not self._enabled:
            logger.warning("EmailOutreachProvider disabled: missing SMTP config")

    def send(self, recipient: str, body: str, subject: str | None = None, **kwargs: Any) -> SendResult:
        if not self._enabled:
            return SendResult(success=False, error_code="not_configured", error_message="Email provider not configured")
        raise NotImplementedError("Real SMTP sending not implemented in MVP")

    def get_status(self, provider_message_id: str) -> DeliveryStatus:
        return DeliveryStatus.unknown
