from __future__ import annotations

import hashlib
import hmac

from app.config import settings


def compute_hmac_sha256(secret: str, payload: bytes) -> str:
    """Compute HMAC-SHA256 hex digest for the given payload and secret."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(
    payload: bytes,
    signature: str | None,
    secret: str,
    allow_mock: bool = False,
) -> bool:
    """
    Verify HMAC-SHA256 signature.

    Args:
        payload: Raw request body bytes
        signature: Signature header value (with or without "sha256=" prefix)
        secret: Shared secret key
        allow_mock: If True and secret is empty, allow in non-production

    Returns:
        True if signature is valid
    """
    if not secret:
        return allow_mock and settings.app_env != "production"

    if not signature:
        return False

    # Accept with or without "sha256=" prefix
    sig = signature.removeprefix("sha256=")
    expected = compute_hmac_sha256(secret, payload)
    return hmac.compare_digest(expected, sig)


def verify_whatsapp_signature(
    payload: bytes,
    signature: str | None,
    allow_mock: bool | None = None,
) -> bool:
    """
    Verify WhatsApp webhook signature using configured app secret.

    Args:
        payload: Raw request body bytes
        signature: X-Hub-Signature-256 header value
        allow_mock: Override mock allowance (default: settings.whatsapp_allow_mock_webhooks)

    Returns:
        True if signature is valid
    """
    if allow_mock is None:
        allow_mock = settings.whatsapp_allow_mock_webhooks
    return verify_signature(
        payload=payload,
        signature=signature,
        secret=settings.whatsapp_app_secret,
        allow_mock=allow_mock,
    )