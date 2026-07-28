from __future__ import annotations

import html
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.campaign import MessageStatus, OutreachMessage
from app.security import generate_csrf_token, log_audit_event, validate_csrf_token

router = APIRouter(prefix="/admin", tags=["admin"])

_NAV = """
<nav style="background:#1f2937;padding:12px 20px;margin-bottom:20px;border-radius:8px">
  <span style="color:#fff;font-weight:bold;margin-right:20px">LeadGen MVP</span>
  <a href="/admin/leads" style="color:#93c5fd;margin-right:16px;text-decoration:none">Leads</a>
  <a href="/admin/landings" style="color:#93c5fd;margin-right:16px;text-decoration:none">Landings</a>
  <a href="/admin/messages" style="color:#93c5fd;margin-right:16px;text-decoration:none">Messages</a>
  <a href="/admin/inbox" style="color:#93c5fd;margin-right:16px;text-decoration:none">Inbox</a>
  <a href="/admin/recovery" style="color:#93c5fd;margin-right:16px;text-decoration:none">Recovery</a>
  <a href="/admin/settings" style="color:#93c5fd;text-decoration:none">Settings</a>
</nav>
"""


def _require_auth(request: Request) -> None:
    auth = request.cookies.get("admin_auth")
    if not auth or not secrets.compare_digest(auth, settings.admin_password):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_csrf(token: str) -> None:
    if not token or not validate_csrf_token(token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@router.get("/messages", response_class=HTMLResponse)
def messages_page(request: Request, db: Session = Depends(get_db)):
    _require_auth(request)
    messages = db.query(OutreachMessage).order_by(OutreachMessage.created_at.desc()).limit(100).all()
    csrf = generate_csrf_token()
    rows: list[str] = []
    for message in messages:
        body = html.escape(message.body[:83] + ("…" if len(message.body) > 83 else ""))
        action = ""
        if message.status == MessageStatus.needs_review.value:
            action = f"""
<form method="post" action="/admin/messages/{message.id}/approve" style="display:inline">
  <input type="hidden" name="csrf_token" value="{csrf}">
  <button type="submit" style="background:#16a34a;color:#fff;border:0;padding:6px 10px;border-radius:5px;cursor:pointer">Одобрить</button>
</form>"""
        rows.append(
            f"<tr><td>{html.escape(message.id)}</td><td>{message.lead_id}</td>"
            f"<td>{html.escape(message.channel)}</td><td><pre>{body}</pre></td>"
            f"<td>{html.escape(message.status)}</td><td>{action}</td></tr>"
        )
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Messages</title>
<style>body{{font-family:system-ui;margin:20px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:7px;text-align:left}}th{{background:#1f2937;color:#fff}}pre{{white-space:pre-wrap;margin:0}}</style></head><body>
{_NAV}<h2>Сообщения на одобрение</h2><table><tr><th>ID</th><th>Lead</th><th>Канал</th><th>Текст</th><th>Статус</th><th>Действие</th></tr>{''.join(rows)}</table></body></html>"""
    return HTMLResponse(page)


@router.get("/messages/{message_id}/approve")
def reject_get_approval(message_id: str, request: Request):
    _require_auth(request)
    raise HTTPException(status_code=405, detail="Use POST to approve messages")


@router.post("/messages/{message_id}/approve")
def approve_message(
    message_id: str,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    _require_auth(request)
    _require_csrf(csrf_token)
    message = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.status != MessageStatus.needs_review.value:
        raise HTTPException(status_code=409, detail=f"Cannot approve message in status {message.status}")

    message.status = MessageStatus.approved.value
    message.approved_by = settings.admin_username
    message.approved_at = datetime.now(timezone.utc)
    log_audit_event(db, "message_approved", "outreach_message", message_id, actor="admin")
    db.commit()
    return RedirectResponse(url="/admin/messages", status_code=303)
