from __future__ import annotations

import enum
from dataclasses import dataclass


class DeliveryStatus(str, enum.Enum):
    unknown = "unknown"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"
    bounced = "bounced"


@dataclass
class SendResult:
    success: bool
    provider_message_id: str | None = None
    error_message: str | None = None
    raw_response: dict | None = None


class OutreachProvider:
    def send(self, recipient: str, body: str, subject: str | None = None) -> SendResult:
        raise NotImplementedError

    def get_status(self, provider_message_id: str) -> DeliveryStatus:
        return DeliveryStatus.unknown
