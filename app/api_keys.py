"""API keys and scopes: hash-only storage, revocation, expiration, rate limiting."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.security import log_audit_event


class ApiScope(str, Enum):
    read = "read"
    review = "review"
    outreach = "outreach"
    admin = "admin"


SCOPE_HIERARCHY: dict[ApiScope, int] = {
    ApiScope.read: 1,
    ApiScope.review: 2,
    ApiScope.outreach: 3,
    ApiScope.admin: 4,
}


class ApiKey:
    """In-memory representation of an API key record.

    In production this would be a SQLAlchemy model in a migration.
    For now we store in a simple table created by migration 007.
    """

    def __init__(
        self,
        id: str,
        key_hash: str,
        name: str,
        scopes: list[str],
        created_at: datetime,
        expires_at: datetime | None,
        revoked: bool,
        created_by: str,
        last_used_at: datetime | None = None,
    ):
        self.id = id
        self.key_hash = key_hash
        self.name = name
        self.scopes = scopes
        self.created_at = created_at
        self.expires_at = expires_at
        self.revoked = revoked
        self.created_by = created_by
        self.last_used_at = last_used_at


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key and its SHA-256 hash.

    Returns (plaintext_key, key_hash).
    """
    key = f"lg_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


def hash_api_key(key: str) -> str:
    """Hash an API key for lookup."""
    return hashlib.sha256(key.encode()).hexdigest()


def create_api_key(
    db: Session,
    name: str,
    scopes: list[str],
    created_by: str,
    expires_in_days: int | None = None,
) -> dict[str, Any]:
    """Create a new API key. Returns key record with plaintext (only time shown)."""
    from app.models.api_key import ApiKeyModel
    import json

    plaintext, key_hash = generate_api_key()
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=expires_in_days)) if expires_in_days else None

    key_id = f"key_{secrets.token_hex(8)}"
    api_key = ApiKeyModel(
        id=key_id,
        key_hash=key_hash,
        name=name,
        scopes_json=json.dumps(scopes),
        expires_at=expires_at,
        revoked=False,
        created_by=created_by,
    )

    log_audit_event(
        db, "api_key_created", "api_key", key_id,
        actor=created_by,
        details={"name": name, "scopes": scopes, "expires_in_days": expires_in_days},
    )
    db.add(api_key)
    db.commit()

    return {
        "id": key_id,
        "key": plaintext,
        "name": name,
        "scopes": scopes,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "message": "Store the key securely. It will not be shown again.",
    }


def verify_api_key(
    db: Session,
    key_hash: str,
    required_scope: str,
) -> tuple[bool, str]:
    """Verify API key: exists, not revoked, not expired, has required scope.

    Returns (is_valid, error_message).
    """
    from app.models.api_key import ApiKeyModel

    record = db.query(ApiKeyModel).filter(ApiKeyModel.key_hash == key_hash).first()
    if not record:
        return False, "Invalid API key"
    if record.revoked:
        return False, "API key has been revoked"
    now = datetime.now(timezone.utc)
    if record.expires_at and record.expires_at < now:
        return False, "API key has expired"

    required_level = SCOPE_HIERARCHY.get(ApiScope(required_scope), 0)
    has_scope = any(
        SCOPE_HIERARCHY.get(ApiScope(s), 0) >= required_level
        for s in record.scopes
    )
    if not has_scope:
        return False, f"Insufficient scope: requires {required_scope}"

    record.last_used_at = now
    db.commit()
    return True, ""


def revoke_api_key(db: Session, key_id: str, actor: str = "admin") -> bool:
    """Revoke an API key."""
    from app.models.api_key import ApiKeyModel

    record = db.query(ApiKeyModel).filter(ApiKeyModel.id == key_id).first()
    if not record:
        return False
    record.revoked = True
    log_audit_event(
        db, "api_key_revoked", "api_key", key_id,
        actor=actor,
        details={"name": record.name},
    )
    db.commit()
    return True
