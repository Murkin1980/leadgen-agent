from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.outreach.phone import PhoneNumberError, PhoneNumberService
from app.outreach.provider import DeliveryStatus, OutreachProvider, SendResult

logger = logging.getLogger(__name__)


class WhatsAppCloudProvider(OutreachProvider):
    """Official WhatsApp Cloud API provider.

    Supports approved templates for first contact and free-form text when the
    caller has already validated the customer-care window.
    """

    def __init__(self, client: httpx.Client | None = None):
        self._enabled = bool(
            settings.whatsapp_cloud_api_token
            and settings.whatsapp_cloud_phone_number_id
        )
        self._url = (
            f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
            f"{settings.whatsapp_cloud_phone_number_id}/messages"
        )
        self._client = client
        if not self._enabled:
            logger.warning("WhatsAppCloudProvider disabled: missing config")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.whatsapp_cloud_api_token}",
            "Content-Type": "application/json",
        }

    def send(
        self,
        recipient: str,
        body: str,
        subject: str | None = None,
        **kwargs: Any,
    ) -> SendResult:
        if not self._enabled:
            return SendResult(
                success=False,
                error_code="not_configured",
                error_message="WhatsApp Cloud not configured",
            )
        try:
            to = PhoneNumberService.provider_recipient(recipient)
        except PhoneNumberError as exc:
            return SendResult(
                success=False,
                error_code="invalid_recipient",
                error_message=str(exc),
            )

        template_name = kwargs.get("template_name")
        language_code = kwargs.get("language_code", "ru")
        components = kwargs.get("components") or []
        service_window_active = bool(kwargs.get("service_window_active"))

        if template_name:
            payload: dict[str, Any] = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                },
            }
            if components:
                payload["template"]["components"] = components
        elif service_window_active:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": body},
            }
        else:
            return SendResult(
                success=False,
                error_code="service_window_closed",
                error_message="Free-form WhatsApp text is outside the service window",
            )

        client = self._client or httpx.Client(timeout=settings.whatsapp_request_timeout_seconds)
        close_client = self._client is None
        try:
            response = client.post(self._url, headers=self.headers, json=payload)
            data = response.json() if response.content else {}
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return SendResult(
                success=False,
                error_code="network_error",
                error_message=type(exc).__name__,
                retryable=True,
            )
        except ValueError:
            data = {}
        finally:
            if close_client:
                client.close()

        if 200 <= response.status_code < 300:
            message_id = None
            messages = data.get("messages") or []
            if messages:
                message_id = messages[0].get("id")
            return SendResult(
                success=True,
                provider_message_id=message_id,
                provider_status="accepted",
                raw_response={"status_code": response.status_code},
            )

        error = data.get("error") or {}
        code = str(error.get("code") or response.status_code)
        retryable = response.status_code == 429 or response.status_code >= 500
        safe_message = str(error.get("message") or "WhatsApp API request failed")[:500]
        logger.warning(
            "WhatsApp send failed recipient=%s status=%s code=%s",
            PhoneNumberService.mask(recipient),
            response.status_code,
            code,
        )
        return SendResult(
            success=False,
            provider_status="failed",
            error_code=code,
            error_message=safe_message,
            retryable=retryable,
            raw_response={"status_code": response.status_code},
        )

    def get_status(self, provider_message_id: str) -> DeliveryStatus:
        # Delivery state is authoritative through signed webhooks.
        return DeliveryStatus.unknown
