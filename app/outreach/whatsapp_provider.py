import logging

from app.config import settings
from app.outreach.provider import OutreachProvider, SendResult, DeliveryStatus

logger = logging.getLogger(__name__)


class WhatsAppCloudProvider(OutreachProvider):
    def __init__(self):
        self._enabled = bool(
            settings.whatsapp_cloud_api_token
            and settings.whatsapp_cloud_phone_number_id
        )
        if not self._enabled:
            logger.warning("WhatsAppCloudProvider disabled: missing config")

    def send(self, recipient: str, body: str, subject: str | None = None) -> SendResult:
        if not self._enabled:
            return SendResult(success=False, error_message="WhatsApp Cloud not configured")
        raise NotImplementedError("Real WhatsApp Cloud sending not implemented in MVP")

    def get_status(self, provider_message_id: str) -> DeliveryStatus:
        return DeliveryStatus.unknown
