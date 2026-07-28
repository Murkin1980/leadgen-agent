from __future__ import annotations

import html
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from rq import Queue
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.campaign import MessageStatus, OutreachMessage
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import LandingPage, LandingStatus, ReviewStatus
from app.models.lead import Lead
from app.security import generate_csrf_token, log_audit_event, validate_csrf_token
from app.workers.connection import redis_conn

recovery_router = APIRouter(prefix="/admin", tags=["admin-recovery"])


def _require_auth(request: Request) -> None:
    auth = request.cookies.get("admin_auth")
    if not auth or not secrets.compare_digest(auth, settings.admin_password):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_csrf(token: str) -> None:
    if not token or not validate_csrf_token(token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def _button(action: str, csrf: str, label: str = "Повторить") -> str:
    return (
        f'<form method="post" action="{html.escape(action)}" style="display:inline">'
        f'<input type="hidden" name="csrf_token" value="{html.escape(csrf)}">'
        f'<button type="submit">{html.escape(label)}</button></form>'
    )


@recovery_router.get("/recovery", response_class=HTMLResponse)
def recovery_page(request: Request, db: Session = Depends(get_db)):
    """Show only failed MVP operations that have a safe manual retry path."""
    _require_auth(request)
    csrf = generate_csrf_token()

    generations = (
        db.query(ContentGeneration)
        .filter(ContentGeneration.status.in_([
            ContentGenerationStatus.failed.value,
            ContentGenerationStatus.rejected.value,
        ]))
        .order_by(ContentGeneration.created_at.desc())
        .limit(50)
        .all()
    )
    landings = (
        db.query(LandingPage)
        .filter(
            LandingPage.status == LandingStatus.failed.value,
            LandingPage.review_status == ReviewStatus.approved.value,
        )
        .order_by(LandingPage.created_at.desc())
        .limit(50)
        .all()
    )
    messages = (
        db.query(OutreachMessage)
        .filter(
            OutreachMessage.status == MessageStatus.failed.value,
            OutreachMessage.retryable.is_(True),
        )
        .order_by(OutreachMessage.created_at.desc())
        .limit(50)
        .all()
    )

    rows: list[str] = []
    for item in generations:
        rows.append(
            "<tr>"
            f"<td>Генерация</td><td>{html.escape(item.id)}</td>"
            f"<td>{item.lead_id}</td><td>{html.escape(item.error_message or '')}</td>"
            f"<td>{_button(f'/admin/recovery/generations/{item.id}/retry', csrf)}</td>"
            "</tr>"
        )
    for item in landings:
        rows.append(
            "<tr>"
            f"<td>Публикация</td><td>{html.escape(item.id)}</td>"
            f"<td>{item.lead_id}</td><td>Публикация завершилась ошибкой</td>"
            f"<td>{_button(f'/admin/recovery/landings/{item.id}/retry', csrf)}</td>"
            "</tr>"
        )
    for item in messages:
        rows.append(
            "<tr>"
            f"<td>Отправка</td><td>{html.escape(item.id)}</td>"
            f"<td>{item.lead_id}</td><td>{html.escape(item.error_message or '')}</td>"
            f"<td>{_button(f'/admin/recovery/messages/{item.id}/retry', csrf)}</td>"
            "</tr>"
        )

    table_rows = "".join(rows) or '<tr><td colspan="5">Нет операций, доступных для повтора.</td></tr>'
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html><head><title>Восстановление MVP</title>
<style>
body{{font-family:system-ui;max-width:1100px;margin:20px auto;padding:20px}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#1f2937;color:#fff}}button{{background:#2563eb;color:#fff;border:0;padding:7px 12px;border-radius:6px;cursor:pointer}}
a{{color:#2563eb}}
</style></head><body>
<p><a href="/admin/leads">← Leads</a> · <a href="/admin/landings">Landings</a> · <a href="/admin/messages">Messages</a></p>
<h2>Восстановление MVP</h2>
<p>Здесь показаны только операции, которые разрешено безопасно повторить. Блокировки политики, DNC, отменённые и terminal/dead-letter операции не отображаются.</p>
<table><tr><th>Операция</th><th>ID</th><th>Lead</th><th>Ошибка</th><th>Действие</th></tr>{table_rows}</table>
</body></html>"""
    )


@recovery_router.post("/recovery/generations/{generation_id}/retry")
def retry_generation(
    generation_id: str,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    _require_auth(request)
    _require_csrf(csrf_token)
    generation = db.query(ContentGeneration).filter(ContentGeneration.id == generation_id).first()
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    if generation.status not in {
        ContentGenerationStatus.failed.value,
        ContentGenerationStatus.rejected.value,
    }:
        raise HTTPException(status_code=409, detail="Generation is not retryable")

    generation.status = ContentGenerationStatus.queued.value
    generation.error_message = None
    generation.started_at = None
    generation.completed_at = None
    log_audit_event(db, "generation_retry_queued", "content_generation", generation_id, actor="admin")
    db.commit()
    Queue("generate_content", connection=redis_conn).enqueue(
        "app.workers.content_generator_worker.run_content_generator",
        generation_id,
    )
    return RedirectResponse(url="/admin/recovery", status_code=303)


@recovery_router.post("/recovery/landings/{landing_id}/retry")
def retry_publication(
    landing_id: str,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    _require_auth(request)
    _require_csrf(csrf_token)
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")
    if not (
        landing.status == LandingStatus.failed.value
        and landing.review_status == ReviewStatus.approved.value
    ):
        raise HTTPException(status_code=409, detail="Landing publication is not retryable")

    lead = db.query(Lead).filter(Lead.id == landing.lead_id).first()
    if not lead or not lead.search_job_id:
        raise HTTPException(status_code=409, detail="Landing has no source job for publication retry")

    landing.status = LandingStatus.approved.value
    log_audit_event(db, "publication_retry_queued", "landing_page", landing_id, actor="admin")
    db.commit()
    Queue("publish", connection=redis_conn).enqueue(
        "app.workers.publisher_worker.run_publisher",
        [landing_id],
        lead.search_job_id,
    )
    return RedirectResponse(url="/admin/recovery", status_code=303)


@recovery_router.post("/recovery/messages/{message_id}/retry")
def retry_message(
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
    if not (
        message.status == MessageStatus.failed.value
        and message.retryable
    ):
        raise HTTPException(status_code=409, detail="Message is not retryable")

    lead = db.query(Lead).filter(Lead.id == message.lead_id).first()
    if not lead or lead.do_not_contact:
        raise HTTPException(status_code=409, detail="Lead is not eligible for retry")

    message.status = MessageStatus.queued.value
    message.error_message = None
    message.next_retry_at = None
    log_audit_event(db, "message_retry_queued", "outreach_message", message_id, actor="admin")
    db.commit()
    Queue("outreach_send", connection=redis_conn).enqueue(
        "app.workers.outreach_sender_worker.run_outreach_sender",
        message_id,
    )
    return RedirectResponse(url="/admin/recovery", status_code=303)
