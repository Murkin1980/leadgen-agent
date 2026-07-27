from app.security.core import (
    clear_login_attempts,
    generate_csrf_token,
    log_audit_event,
    record_login_attempt,
    validate_csrf_token,
    verify_login_attempt,
    verify_webhook_signature,
)
from app.security.webhook_signature import (
    compute_hmac_sha256,
    verify_signature,
    verify_whatsapp_signature,
)

__all__ = [
    "clear_login_attempts",
    "compute_hmac_sha256",
    "generate_csrf_token",
    "log_audit_event",
    "record_login_attempt",
    "validate_csrf_token",
    "verify_login_attempt",
    "verify_signature",
    "verify_webhook_signature",
    "verify_whatsapp_signature",
]


def _import_sanity_check() -> None:
    """Verify all public symbols resolve at import time."""
    for name in __all__:
        if name not in globals():
            raise ImportError(f"app.security failed to export {name}")


_import_sanity_check()
