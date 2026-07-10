"""Phase 07 production routes: readiness, inbox, backup, retention, template sync, API keys, pilot."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.metrics import (
    active_workers,
    api_request_latency,
    db_errors_total,
    deployments_total,
    landing_pages_published,
    leads_collected_total,
    messages_dead_letter_total,
    messages_delivered_total,
    messages_failed_total,
    messages_read_total,
    messages_retried_total,
    messages_sent_total,
    queue_depth,
    webhook_duplicate_total,
    webhook_processed_total,
    metrics_router,
)
from app.pilot import (
    is_pilot_mode,
    pilot_kill_switch,
    pilot_report,
    pilot_status,
    pilot_validate_lead_count,
    pilot_validate_message,
)
from app.security import log_audit_event

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Readiness ─────────────────────────────────────────────────────

@router.get("/readiness")
def readiness(db: Session = Depends(get_db)):
    """Kubernetes-style readiness probe.

    Returns HTTP 503 if any critical dependency is down.
    """
    import sqlalchemy
    from app.workers.connection import redis_conn

    checks: dict[str, dict] = {}

    # PostgreSQL
    try:
        with db.get_bind().connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        checks["postgres"] = {"ok": True}
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": str(exc)[:200]}

    # Redis
    try:
        redis_conn.ping()
        checks["redis"] = {"ok": True}
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": str(exc)[:200]}

    # Alembic migration revision
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        checks["alembic"] = {"ok": True, "revision": heads[0] if heads else None}
    except Exception as exc:
        checks["alembic"] = {"ok": False, "error": str(exc)[:200]}

    # Outreach mode
    outreach_mode = getattr(settings, "outreach_mode", "disabled")
    checks["outreach_mode"] = {"ok": True, "mode": outreach_mode}

    # WhatsApp config
    whatsapp_configured = bool(settings.whatsapp_cloud_api_token and settings.whatsapp_cloud_business_account_id)
    checks["whatsapp"] = {"ok": True, "configured": whatsapp_configured}

    all_ok = all(c.get("ok", False) for c in checks.values())
    status_code = 200 if all_ok else 503

    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.7.0",
    }


# ── Template Sync ─────────────────────────────────────────────────

@router.post("/templates/sync")
def sync_templates_endpoint(
    provider: str = "mock",
    db: Session = Depends(get_db),
):
    from app.outreach.template_sync import MockTemplateSyncAdapter, MetaTemplateSyncAdapter, sync_templates

    if provider == "meta":
        adapter = MetaTemplateSyncAdapter()
    else:
        adapter = MockTemplateSyncAdapter()

    result = sync_templates(db, adapter)
    log_audit_event(
        db, "template_sync", "whatsapp_templates", "bulk",
        actor="system",
        details={"created": result.created, "updated": result.updated, "errors": result.errors},
    )
    return {
        "created": result.created,
        "updated": result.updated,
        "errors": result.errors,
    }


@router.get("/templates")
def list_templates(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    from app.models.whatsapp import WhatsAppTemplate
    q = db.query(WhatsAppTemplate)
    if status:
        q = q.filter(WhatsAppTemplate.status == status)
    return q.order_by(WhatsAppTemplate.created_at.desc()).limit(limit).all()


# ── Operator Inbox ────────────────────────────────────────────────

@router.get("/inbox/conversations")
def list_conversations_endpoint(
    lead_id: int | None = None,
    has_unread: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    from app.outreach.inbox import list_conversations
    return list_conversations(db, lead_id=lead_id, has_unread=has_unread, limit=limit, offset=offset)


@router.get("/inbox/conversations/{lead_id}")
def get_conversation_history_endpoint(
    lead_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    from app.outreach.inbox import get_conversation_history
    history = get_conversation_history(db, lead_id, limit=limit)
    if not history:
        raise HTTPException(status_code=404, detail="No conversation history")
    return {"lead_id": lead_id, "messages": history}


@router.post("/inbox/messages/{message_id}/handled")
def mark_handled_endpoint(
    message_id: str,
    db: Session = Depends(get_db),
):
    from app.outreach.inbox import mark_handled
    ok = mark_handled(db, message_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message_id": message_id, "status": "handled"}


@router.get("/inbox/can-reply/{lead_id}")
def can_reply_endpoint(
    lead_id: int,
    db: Session = Depends(get_db),
):
    from app.outreach.inbox import can_reply_manually
    allowed, reason = can_reply_manually(db, lead_id)
    return {"lead_id": lead_id, "can_reply": allowed, "reason": reason}


@router.post("/inbox/reply/{lead_id}")
def reply_to_lead_endpoint(
    lead_id: int,
    body: str = "",
    template_name: str | None = None,
    db: Session = Depends(get_db),
):
    from app.outreach.inbox import can_reply_manually, send_template_reply
    allowed, reason = can_reply_manually(db, lead_id)
    if not allowed:
        raise HTTPException(status_code=403, detail=f"Cannot reply: {reason}")

    ok, result = send_template_reply(db, lead_id, body, template_name=template_name)
    if not ok:
        raise HTTPException(status_code=400, detail=result)
    return {"message_id": result, "status": "needs_review"}


@router.post("/inbox/template-reply/{lead_id}")
def template_reply_endpoint(
    lead_id: int,
    body: str = "",
    template_name: str | None = None,
    db: Session = Depends(get_db),
):
    from app.outreach.inbox import send_template_reply
    ok, result = send_template_reply(db, lead_id, body, template_name=template_name)
    if not ok:
        raise HTTPException(status_code=400, detail=result)
    return {"message_id": result, "status": "needs_review"}


# ── Backup & Restore ─────────────────────────────────────────────

@router.post("/backup/create")
def create_backup_endpoint(
    output_dir: str = "backups",
    db: Session = Depends(get_db),
):
    from app.backup import create_backup
    manifest = create_backup(output_dir)
    log_audit_event(db, "backup_created", "backup", "full", actor="admin")
    return {"manifest": manifest}


@router.post("/backup/verify")
def verify_backup_endpoint(backup_dir: str = "backups"):
    from app.backup import verify_backup
    ok, errors = verify_backup(backup_dir)
    return {"valid": ok, "errors": errors}


@router.post("/backup/restore")
def restore_backup_endpoint(
    backup_dir: str = "backups",
    target_database_url: str | None = None,
    db: Session = Depends(get_db),
):
    if not target_database_url:
        target_database_url = settings.database_url
    from app.backup import restore_database
    result = restore_database(backup_dir, target_database_url)
    log_audit_event(db, "backup_restored", "backup", "full", actor="admin", details=result)
    return result


# ── Retention ─────────────────────────────────────────────────────

@router.get("/retention/config")
def get_retention_config_endpoint():
    from app.retention import get_retention_config
    return get_retention_config()


@router.get("/retention/preview")
def retention_preview_endpoint(db: Session = Depends(get_db)):
    from app.retention import purge_preview
    return purge_preview(db)


@router.post("/retention/execute")
def retention_execute_endpoint(
    dry_run: bool = True,
    actor: str = "admin",
    db: Session = Depends(get_db),
):
    from app.retention import purge_execute
    return purge_execute(db, actor=actor, dry_run=dry_run)


@router.post("/retention/anonymize/{lead_id}")
def anonymize_lead_endpoint(
    lead_id: int,
    actor: str = "admin",
    db: Session = Depends(get_db),
):
    from app.retention import anonymize_lead
    ok = anonymize_lead(db, lead_id, actor=actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"lead_id": lead_id, "status": "anonymized"}


# ── API Keys ──────────────────────────────────────────────────────

@router.post("/api-keys")
def create_api_key_endpoint(
    name: str = "",
    scopes: str = "read",
    expires_in_days: int | None = None,
    db: Session = Depends(get_db),
):
    from app.api_keys import create_api_key
    scope_list = [s.strip() for s in scopes.split(",")]
    result = create_api_key(db, name=name, scopes=scope_list, created_by="admin", expires_in_days=expires_in_days)
    return result


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key_endpoint(
    key_id: str,
    db: Session = Depends(get_db),
):
    from app.api_keys import revoke_api_key
    ok = revoke_api_key(db, key_id, actor="admin")
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"key_id": key_id, "status": "revoked"}


# ── Pilot Mode ────────────────────────────────────────────────────

@router.get("/pilot/status")
def pilot_status_endpoint(db: Session = Depends(get_db)):
    return pilot_status(db)


@router.get("/pilot/report")
def pilot_report_endpoint(db: Session = Depends(get_db)):
    return pilot_report(db)


@router.post("/pilot/kill-switch")
def pilot_kill_switch_endpoint(
    actor: str = "admin",
    db: Session = Depends(get_db),
):
    return pilot_kill_switch(db, actor=actor)


# ── Metrics ───────────────────────────────────────────────────────

router.include_router(metrics_router)


# ── Dead Letter ───────────────────────────────────────────────────

@router.get("/dead-letters")
def list_dead_letters_endpoint(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    from app.outreach.dead_letter import list_dead_letters
    return list_dead_letters(db, limit=limit, offset=offset)


@router.post("/dead-letters/{message_id}/requeue")
def requeue_dead_letter_endpoint(
    message_id: str,
    db: Session = Depends(get_db),
):
    from app.outreach.dead_letter import requeue_dead_letter
    ok, reason = requeue_dead_letter(db, message_id)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    return {"message_id": message_id, "status": "requeued"}


@router.post("/dead-letters/{message_id}/cancel")
def cancel_dead_letter_endpoint(
    message_id: str,
    actor: str = "admin",
    db: Session = Depends(get_db),
):
    from app.outreach.dead_letter import cancel_dead_letter
    ok = cancel_dead_letter(db, message_id, actor=actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message_id": message_id, "status": "cancelled"}
