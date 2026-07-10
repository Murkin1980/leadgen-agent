from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


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
    provider_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    raw_response: dict[str, Any] = field(default_factory=dict)


class OutreachProvider:
    def send(
        self,
        recipient: str,
        body: str,
        subject: str | None = None,
        **kwargs: Any,
    ) -> SendResult:
        raise NotImplementedError

    def get_status(self, provider_message_id: str) -> DeliveryStatus:
        return DeliveryStatus.unknown
