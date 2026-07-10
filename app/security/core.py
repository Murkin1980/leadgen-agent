from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.audit import AuditLog


_csrf_tokens: dict[str, float] = {}
_login_attempts: dict[str, list[float]] = {}


def generate_csrf_token() -> str:
    token = secrets.token_hex(32)
    _csrf_tokens[token] = time.time()
    return token


def validate_csrf_token(token: str) -> bool:
    if not token or token not in _csrf_tokens:
        return False
    created = _csrf_tokens.pop(token, 0)
    return (time.time() - created) < 3600


def verify_login_attempt(ip: str) -> bool:
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < 300]
    _login_attempts[ip] = attempts
    return len(attempts) < 5


def record_login_attempt(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


def clear_login_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)


def verify_webhook_signature(
    payload: bytes, signature: str | None, secret: str
) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.HMAC(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


def log_audit_event(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: str,
    actor: str | None = None,
    details: dict | None = None,
) -> None:
    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        details_json=json.dumps(details, ensure_ascii=False) if details else None,
    )
    db.add(entry)