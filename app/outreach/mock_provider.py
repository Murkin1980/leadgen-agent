import uuid
from app.outreach.provider import OutreachProvider, SendResult, DeliveryStatus


class MockOutreachProvider(OutreachProvider):
    def __init__(self):
        self._sent: dict[str, dict] = {}
        self._statuses: dict[str, DeliveryStatus] = {}

    def send(self, recipient: str, body: str, subject: str | None = None) -> SendResult:
        msg_id = f"mock_{uuid.uuid4().hex[:12]}"
        self._sent[msg_id] = {
            "recipient": recipient,
            "body": body,
            "subject": subject,
        }
        self._statuses[msg_id] = DeliveryStatus.sent
        return SendResult(
            success=True,
            provider_message_id=msg_id,
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
