import uuid
from typing import Any

from app.outreach.provider import DeliveryStatus, OutreachProvider, SendResult


class MockOutreachProvider(OutreachProvider):
    def __init__(self):
        self._sent: dict[str, dict] = {}
        self._statuses: dict[str, DeliveryStatus] = {}

    def send(
        self,
        recipient: str,
        body: str,
        subject: str | None = None,
        **kwargs: Any,
    ) -> SendResult:
        msg_id = f"mock_{uuid.uuid4().hex[:12]}"
        self._sent[msg_id] = {
            "recipient": recipient,
            "body": body,
            "subject": subject,
            "metadata": kwargs,
        }
        self._statuses[msg_id] = DeliveryStatus.sent
        return SendResult(
            success=True,
            provider_message_id=msg_id,
            provider_status="sent",
            raw_response={"mock": True, "message_id": msg_id},
        )

    def get_status(self, provider_message_id: str) -> DeliveryStatus:
        return self._statuses.get(provider_message_id, DeliveryStatus.unknown)

    def simulate_delivered(self, provider_message_id: str) -> None:
        self._statuses[provider_message_id] = DeliveryStatus.delivered

    def simulate_read(self, provider_message_id: str) -> None:
        self._statuses[provider_message_id] = DeliveryStatus.read

    def simulate_failed(self, provider_message_id: str) -> None:
        self._statuses[provider_message_id] = DeliveryStatus.failed

    def simulate_reply(self, provider_message_id: str) -> None:
        self._statuses[provider_message_id] = DeliveryStatus.read
