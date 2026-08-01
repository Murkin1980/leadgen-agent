from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.campaign import OutreachMessage, MessageStatus
from app.models.content_generation import ContentGeneration
from app.models.landing_page import (
    ChangeSource,
    LandingPage,
    LandingPageVersion,
    LandingStatus,
    ReviewStatus,
)
from app.models.lead import Lead
from app.models.whatsapp import InboundMessage, InboundMessageStatus
from app.security import generate_csrf_token, validate_csrf_token, log_audit_event
from app.workers.enricher_worker import run_enricher

admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _retry_banner(request: Request) -> str:
    """Small colored banner reading ?retry=ok|error&msg=... from the query
    string. No session/flash-message framework exists in this admin UI,
    so a redirect query param is the minimal way to show clear feedback
    after a POST action without adding new infrastructure."""
    retry = request.query_params.get("retry")
    if not retry:
        return ""
    msg = request.query_params.get("msg", "")
    if retry == "ok":
        color = "#16a34a"
        text = msg or "Готово"
    else:
        color = "#dc2626"
        text = msg or "Ошибка"
    return f'<div style="background:{color};color:#fff;padding:10px 16px;border-radius:8px;margin-bottom:16px">{text}</div>'

_MVP_NAV = """
<nav style="background:#1f2937;padding:12px 20px;margin-bottom:20px;border-radius:8px">
  <span style="color:#fff;font-weight:bold;margin-right:20px">LeadGen MVP</span>
  <a href="/admin/leads" style="color:#93c5fd;margin-right:16px;text-decoration:none">Leads</a>
  <a href="/admin/landings" style="color:#93c5fd;margin-right:16px;text-decoration:none">Landings</a>
  <a href="/admin/messages" style="color:#93c5fd;margin-right:16px;text-decoration:none">Messages</a>
  <a href="/admin/inbox" style="color:#93c5fd;margin-right:16px;text-decoration:none">Inbox</a>
  <a href="/admin/settings" style="color:#93c5fd;text-decoration:none">Settings</a>
</nav>
"""


def _check_auth(request: Request) -> bool:
    auth = request.cookies.get("admin_auth")
    if not auth:
        return False
    return secrets.compare_digest(auth, settings.admin_password)


def _require_auth(request: Request):
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_csrf(csrf_token: str = ""):
    if not csrf_token or not validate_csrf_token(csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@admin_router.get("/login", response_class=HTMLResponse)
def login_page():
    html = """<!DOCTYPE html>
<html><head><title>Login</title>
<style>
body{font-family:system-ui;max-width:400px;margin:100px auto;padding:20px}
input[type=password]{width:100%;padding:10px;margin:10px 0;box-sizing:border-box}
button{background:#1f2937;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;width:100%}
</style></head><body>
<h2>Admin Login</h2>
<form method="post" action="/admin/login">
<input type="password" name="password" placeholder="Password" autofocus>
<button type="submit">Login</button>
</form>
</body></html>"""
    return HTMLResponse(content=html)


@admin_router.post("/login")
def do_login(password: str = Form(...), response: Response = None):
    if not secrets.compare_digest(password, settings.admin_password):
        raise HTTPException(status_code=401, detail="Invalid password")
    resp = RedirectResponse(url="/admin/leads", status_code=302)
    resp.set_cookie("admin_auth", password, httponly=True, max_age=3600)
    return resp


# ── 1. Leads ─────────────────────────────────────────────────────

@admin_router.get("/leads", response_class=HTMLResponse)
def admin_leads(request: Request, db: Session = Depends(get_db)):
    _require_auth(request)
    leads = db.query(Lead).order_by(Lead.id.desc()).limit(100).all()
    csrf = generate_csrf_token()
    rows = ""
    for l in leads:
        actions = f'<a href="/admin/landings?lead_id={l.id}">landings</a>'
        if l.status == "failed":
            actions += f'''
<form method="post" action="/admin/leads/{l.id}/retry-enrichment" style="display:inline;margin-left:8px">
<input type="hidden" name="csrf_token" value="{csrf}">
<button type="submit" style="background:#f59e0b;color:#fff;border:none;padding:2px 8px;border-radius:4px;cursor:pointer">Повторить</button>
</form>'''
        rows += f"""<tr>
<td>{l.id}</td><td>{l.name}</td><td>{l.city}</td><td>{l.phone}</td>
<td>{l.stage}</td><td>{l.status}</td>
<td>{actions}</td>
</tr>"""
    html = f"""<!DOCTYPE html>
<html><head><title>Leads</title>
<style>table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#1f2937;color:#fff}}a{{color:#2563eb}}</style></head><body>
{_MVP_NAV}
{_retry_banner(request)}
<table><tr><th>ID</th><th>Name</th><th>City</th><th>Phone</th><th>Stage</th><th>Status</th><th>Actions</th></tr>
{rows}</table>
</body></html>"""
    return HTMLResponse(content=html)


@admin_router.post("/leads/{lead_id}/retry-enrichment")
def admin_retry_enrichment(
    lead_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Retry enrichment for a lead stuck in failed status. State-validated:
    only actually retries leads that are in 'failed' status; runs the real
    worker function synchronously so the operator gets an immediate result
    without needing a live Redis/RQ worker for this one-off admin action."""
    _require_auth(request)
    _require_csrf(csrf_token)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.status != "failed":
        return RedirectResponse(
            url="/admin/leads?retry=error&msg=Лид+не+в+статусе+failed", status_code=302
        )

    log_audit_event(db, "enrichment_retry_requested", "lead", str(lead_id), actor="admin")
    db.commit()

    run_enricher([lead_id], lead.search_job_id)

    db.refresh(lead)
    if lead.status == "enriched":
        return RedirectResponse(
            url="/admin/leads?retry=ok&msg=Обогащение+повторено+успешно", status_code=302
        )
    return RedirectResponse(
        url="/admin/leads?retry=error&msg=Повтор+не+удался,+см.+журнал+аудита", status_code=302
    )


@admin_router.get("/leads/{lead_id}", response_class=HTMLResponse)
def admin_lead_detail(lead_id: int, request: Request, db: Session = Depends(get_db)):
    _require_auth(request)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    from app.models.stage import LeadStageHistory
    history = db.query(LeadStageHistory).filter(
        LeadStageHistory.lead_id == lead_id
    ).order_by(LeadStageHistory.created_at.desc()).all()
    history_html = ""
    for h in history:
        history_html += f"<li>{h.from_stage} → {h.to_stage} by {h.changed_by or 'system'} — {h.reason or ''}</li>"
    dnc = "YES" if lead.do_not_contact else "No"

    csrf = generate_csrf_token()
    latest_gen = (
        db.query(ContentGeneration)
        .filter(ContentGeneration.lead_id == lead_id)
        .order_by(ContentGeneration.created_at.desc())
        .first()
    )
    gen_html = "<p>No content generation yet</p>"
    if latest_gen:
        gen_html = f"<p><b>Last generation:</b> {latest_gen.status}"
        if latest_gen.error_message:
            gen_html += f" — {latest_gen.error_message}"
        gen_html += "</p>"
        if latest_gen.status == "failed":
            gen_html += f'''
<form method="post" action="/admin/leads/{lead_id}/retry-content-generation" style="display:inline">
<input type="hidden" name="csrf_token" value="{csrf}">
<button type="submit" style="background:#f59e0b;color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer">Повторить генерацию</button>
</form>'''

    html = f"""<!DOCTYPE html>
<html><head><title>Lead {lead_id}</title>
<style>body{{font-family:system-ui;max-width:800px;margin:20px auto;padding:20px}}
.box{{background:#f3f4f6;padding:16px;border-radius:8px;margin:12px 0}}</style></head><body>
{_MVP_NAV}
{_retry_banner(request)}
<h2>{lead.name}</h2>
<div class="box">
<p><b>ID:</b> {lead.id} | <b>City:</b> {lead.city} | <b>Phone:</b> {lead.phone}</p>
<p><b>Stage:</b> {lead.stage} | <b>Status:</b> {lead.status} | <b>Score:</b> {lead.qualification_score}</p>
<p><b>Do Not Contact:</b> {dnc} {f'({lead.do_not_contact_reason})' if lead.do_not_contact_reason else ''}</p>
</div>
<div class="box">
{gen_html}
</div>
<h3>Stage History</h3>
<ul>{history_html or '<li>No history</li>'}</ul>
</body></html>"""
    return HTMLResponse(content=html)


@admin_router.post("/leads/{lead_id}/retry-content-generation")
def admin_retry_content_generation(
    lead_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Retry content generation for a lead whose last generation failed.
    Reuses the same idempotency-guarded creation path as
    POST /leads/{id}/content-generations (blocks if one is already in
    flight, reuses the lead's existing landing rather than creating a
    competing one), then runs the real worker synchronously so the
    operator sees an immediate result."""
    _require_auth(request)
    _require_csrf(csrf_token)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    latest_gen = (
        db.query(ContentGeneration)
        .filter(ContentGeneration.lead_id == lead_id)
        .order_by(ContentGeneration.created_at.desc())
        .first()
    )
    if not latest_gen or latest_gen.status != "failed":
        return RedirectResponse(
            url=f"/admin/leads/{lead_id}?retry=error&msg=Нет+неудачной+генерации+для+повтора",
            status_code=302,
        )

    from app.api.routes import _create_content_generation_record
    from app.schemas.content_generation import ContentGenerationCreate
    from app.workers.content_generator_worker import run_content_generator

    try:
        new_gen = _create_content_generation_record(lead_id, ContentGenerationCreate(), db)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/admin/leads/{lead_id}?retry=error&msg={e.detail}", status_code=302
        )

    log_audit_event(db, "content_generation_retry_requested", "lead", str(lead_id), actor="admin")
    db.commit()

    run_content_generator(new_gen.id)

    db.refresh(new_gen)
    if new_gen.status == "succeeded":
        return RedirectResponse(
            url=f"/admin/leads/{lead_id}?retry=ok&msg=Генерация+повторена+успешно",
            status_code=302,
        )
    return RedirectResponse(
        url=f"/admin/leads/{lead_id}?retry=error&msg=Повтор+не+удался,+см.+журнал",
        status_code=302,
    )


# ── 2. Landings on Review ───────────────────────────────────────

@admin_router.get("/landings", response_class=HTMLResponse)
def admin_landings(request: Request, lead_id: int | None = None, db: Session = Depends(get_db)):
    _require_auth(request)
    q = db.query(LandingPage).order_by(LandingPage.created_at.desc())
    if lead_id:
        q = q.filter(LandingPage.lead_id == lead_id)
    landings = q.limit(100).all()
    rows = ""
    for lp in landings:
        review_badge = lp.review_status
        if lp.review_status == "needs_review":
            review_badge = '<span style="background:#f59e0b;color:#fff;padding:2px 8px;border-radius:4px">needs_review</span>'
        elif lp.review_status == "approved":
            review_badge = '<span style="background:#16a34a;color:#fff;padding:2px 8px;border-radius:4px">approved</span>'
        elif lp.review_status == "published":
            review_badge = '<span style="background:#2563eb;color:#fff;padding:2px 8px;border-radius:4px">published</span>'
        rows += f"""<tr>
<td>{lp.id}</td><td>{lp.lead_id}</td><td>{lp.slug}</td>
<td>{review_badge}</td><td>{lp.status}</td>
<td><a href="/admin/landings/{lp.id}">review</a></td>
</tr>"""
    html = f"""<!DOCTYPE html>
<html><head><title>Landings</title>
<style>table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#1f2937;color:#fff}}a{{color:#2563eb}}</style></head><body>
{_MVP_NAV}
<h2>Landings</h2>
<table><tr><th>ID</th><th>Lead</th><th>Slug</th><th>Review</th><th>Status</th><th>Actions</th></tr>
{rows}</table>
</body></html>"""
    return HTMLResponse(content=html)


@admin_router.get("/landings/{landing_id}", response_class=HTMLResponse)
def admin_landing_detail(landing_id: str, request: Request, db: Session = Depends(get_db)):
    _require_auth(request)
    lp = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Landing not found")
    lead = db.query(Lead).filter(Lead.id == lp.lead_id).first()
    profile_data = {}
    if lp.profile_json:
        try:
            profile_data = json.loads(lp.profile_json)
        except (json.JSONDecodeError, AttributeError):
            pass

    lead_info = ""
    if lead:
        lead_info = f"""<p><b>Lead:</b> {lead.name} | City: {lead.city} | Phone: {lead.phone}</p>"""

    csrf = generate_csrf_token()
    preview = ""
    if lp.preview_url:
        preview = f'<iframe src="{lp.preview_url}" width="100%" height="600" frameborder="0"></iframe>'

    retry_publish_btn = ""
    if lp.status == "failed" and lp.review_status == "approved":
        retry_publish_btn = f'''
<form method="post" action="/admin/landings/{landing_id}/retry-publish" style="display:inline">
<input type="hidden" name="csrf_token" value="{csrf}">
<button class="btn" style="background:#f59e0b;color:#fff" type="submit">Повторить публикацию</button></form>'''

    html = f"""<!DOCTYPE html>
<html><head><title>Landing {landing_id}</title>
<style>body{{font-family:system-ui;max-width:900px;margin:20px auto;padding:20px}}
.box{{background:#f3f4f6;padding:16px;border-radius:8px;margin:12px 0}}
.btn{{padding:8px 16px;border:none;border-radius:6px;cursor:pointer;margin:4px}}
.btn-approve{{background:#16a34a;color:#fff}}
.btn-reject{{background:#dc2626;color:#fff}}</style></head><body>
{_MVP_NAV}
{_retry_banner(request)}
<h2>Landing {landing_id}</h2>
{lead_info}
<div class="box"><b>Review:</b> {lp.review_status} | <b>Status:</b> {lp.status}</div>
<form method="post" action="/admin/landings/{landing_id}/approve" style="display:inline">
<input type="hidden" name="csrf_token" value="{csrf}">
<button class="btn btn-approve" type="submit">Approve</button></form>
<form method="post" action="/admin/landings/{landing_id}/reject" style="display:inline">
<input type="hidden" name="csrf_token" value="{csrf}">
<input name="reason" placeholder="Reason" value="Не подходит">
<button class="btn btn-reject" type="submit">Reject</button></form>
{retry_publish_btn}
{preview}
</body></html>"""
    return HTMLResponse(content=html)


@admin_router.post("/landings/{landing_id}/retry-publish")
def admin_retry_publish(
    landing_id: str,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Retry publication for a landing stuck in failed status. Reuses the
    exact same code path as POST /landings/{id}/publish (the real,
    single-landing publish endpoint the MVP flow actually uses -- not the
    job-based batch run_publisher worker, which needs a SearchJob and
    isn't what a single "retry this one landing" click maps to)."""
    _require_auth(request)
    _require_csrf(csrf_token)
    lp = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Landing not found")
    if lp.status != "failed":
        return RedirectResponse(
            url=f"/admin/landings/{landing_id}?retry=error&msg=Лендинг+не+в+статусе+failed",
            status_code=302,
        )
    if lp.review_status != "approved":
        return RedirectResponse(
            url=f"/admin/landings/{landing_id}?retry=error&msg=Лендинг+должен+быть+approved",
            status_code=302,
        )

    from app.api.routes import publish_landing

    log_audit_event(db, "publish_retry_requested", "landing_page", landing_id, actor="admin")
    db.commit()

    try:
        publish_landing(landing_id, db)
    except HTTPException as e:
        return RedirectResponse(
            url=f"/admin/landings/{landing_id}?retry=error&msg={e.detail}", status_code=302
        )

    db.refresh(lp)
    if lp.status == "published":
        return RedirectResponse(
            url=f"/admin/landings/{landing_id}?retry=ok&msg=Публикация+повторена+успешно",
            status_code=302,
        )
    return RedirectResponse(
        url=f"/admin/landings/{landing_id}?retry=error&msg=Повтор+не+удался,+см.+журнал",
        status_code=302,
    )


@admin_router.post("/landings/{landing_id}/approve")
def admin_approve_landing(
    landing_id: str,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    _require_auth(request)
    _require_csrf(csrf_token)
    lp = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Landing not found")
    lp.review_status = ReviewStatus.approved.value
    lp.status = LandingStatus.approved.value
    from datetime import datetime, timezone
    lp.approved_at = datetime.now(timezone.utc)
    lp.approved_by = settings.admin_username
    db.commit()
    return RedirectResponse(url=f"/admin/landings/{landing_id}", status_code=302)


@admin_router.post("/landings/{landing_id}/reject")
def admin_reject_landing(
    landing_id: str,
    request: Request,
    reason: str = Form("Не подходит"),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    _require_auth(request)
    _require_csrf(csrf_token)
    lp = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Landing not found")
    lp.review_status = ReviewStatus.rejected.value
    lp.status = LandingStatus.failed.value
    lp.review_note = reason
    db.commit()
    return RedirectResponse(url=f"/admin/landings/{landing_id}", status_code=302)


# ── 3. Messages on Approval ────────────────────────────────────

@admin_router.get("/messages", response_class=HTMLResponse)
def admin_messages(request: Request, db: Session = Depends(get_db)):
    _require_auth(request)
    messages = (
        db.query(OutreachMessage)
        .order_by(OutreachMessage.created_at.desc())
        .limit(100)
        .all()
    )
    rows = ""
    csrf = generate_csrf_token()
    for m in messages:
        body_preview = (m.body[:80] + "...") if len(m.body) > 80 else m.body
        body_preview = body_preview.replace("<", "&lt;")
        actions = ""
        if m.status == "needs_review":
            actions = f'''<a href="/admin/messages/{m.id}/approve?csrf_token={csrf}" style="color:#16a34a">approve</a>'''
        elif m.status == "dead_letter" and m.retryable:
            # No retry action for 'blocked' messages (permanent policy
            # blocks -- DNC, sandbox mismatch, invalid recipient) or for
            # dead_letter messages where retryable is False: those must
            # not be retriable from here, per section 4.4's requirement.
            actions = f'''
<form method="post" action="/admin/messages/{m.id}/retry-send" style="display:inline">
<input type="hidden" name="csrf_token" value="{csrf}">
<button type="submit" style="background:#f59e0b;color:#fff;border:none;padding:2px 8px;border-radius:4px;cursor:pointer">Повторить</button>
</form>'''
        rows += f"""<tr>
<td>{m.id}</td><td>{m.lead_id}</td><td>{m.channel}</td>
<td style="max-width:300px"><pre style="margin:0;font-size:12px">{body_preview}</pre></td>
<td>{m.status}</td><td>{actions}</td>
</tr>"""
    html = f"""<!DOCTYPE html>
<html><head><title>Messages</title>
<style>table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:6px;text-align:left}}
th{{background:#1f2937;color:#fff}}a{{color:#2563eb}}</style></head><body>
{_MVP_NAV}
{_retry_banner(request)}
<h2>Messages on Approval</h2>
<table><tr><th>ID</th><th>Lead</th><th>Channel</th><th>Body</th><th>Status</th><th>Actions</th></tr>
{rows}</table>
</body></html>"""
    return HTMLResponse(content=html)


@admin_router.post("/messages/{message_id}/retry-send")
def admin_retry_send(
    message_id: str,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Retry a dead-letter message. Reuses the existing dead-letter
    requeue workflow (app.outreach.dead_letter.requeue_dead_letter),
    which re-checks do_not_contact, consent (in production mode), sandbox
    allowlist (in sandbox mode), phone validity, and outreach_enabled
    before allowing the retry -- so a retry can never bypass those
    checks. Then runs the real sender worker synchronously so the
    operator sees an immediate result."""
    _require_auth(request)
    _require_csrf(csrf_token)

    from app.outreach.dead_letter import requeue_dead_letter
    from app.workers.outreach_sender_worker import run_outreach_sender

    ok, reason = requeue_dead_letter(db, message_id, actor="admin")
    if not ok:
        return RedirectResponse(
            url=f"/admin/messages?retry=error&msg={reason}", status_code=302
        )

    run_outreach_sender(message_id)

    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if msg and msg.status == "sent":
        return RedirectResponse(
            url="/admin/messages?retry=ok&msg=Сообщение+отправлено+повторно", status_code=302
        )
    return RedirectResponse(
        url="/admin/messages?retry=error&msg=Повтор+поставлен+в+очередь,+но+не+завершён",
        status_code=302,
    )


@admin_router.get("/messages/{message_id}/approve")
def admin_approve_message_link(
    message_id: str,
    request: Request,
    csrf_token: str = "",
    db: Session = Depends(get_db),
):
    """Approve via GET link (from messages list)."""
    _require_auth(request)
    _require_csrf(csrf_token)
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.status = MessageStatus.approved.value
    msg.approved_by = settings.admin_username
    from datetime import datetime, timezone
    msg.approved_at = datetime.now(timezone.utc)
    log_audit_event(db, "message_approved", "outreach_message", message_id, actor="admin")
    db.commit()
    return RedirectResponse(url="/admin/messages", status_code=302)


@admin_router.post("/messages/{message_id}/approve")
def admin_approve_message(
    message_id: str,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    _require_auth(request)
    _require_csrf(csrf_token)
    msg = db.query(OutreachMessage).filter(OutreachMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.status = MessageStatus.approved.value
    msg.approved_by = settings.admin_username
    from datetime import datetime, timezone
    msg.approved_at = datetime.now(timezone.utc)
    log_audit_event(db, "message_approved", "outreach_message", message_id, actor="admin")
    db.commit()
    return RedirectResponse(url="/admin/messages", status_code=302)


# ── 4. Inbox (Inbound Responses) ───────────────────────────────

@admin_router.get("/inbox", response_class=HTMLResponse)
def admin_inbox(request: Request, db: Session = Depends(get_db)):
    _require_auth(request)
    inbounds = (
        db.query(InboundMessage)
        .order_by(InboundMessage.received_at.desc())
        .limit(100)
        .all()
    )
    rows = ""
    for im in inbounds:
        lead = db.query(Lead).filter(Lead.id == im.lead_id).first() if im.lead_id else None
        lead_name = lead.name if lead else "(unknown)"
        text_preview = (im.text_body[:100] + "...") if im.text_body and len(im.text_body) > 100 else (im.text_body or "")
        text_preview = text_preview.replace("<", "&lt;")
        status_badge = im.status
        if im.status == "new":
            status_badge = f'<span style="background:#f59e0b;color:#fff;padding:2px 8px;border-radius:4px">{im.status}</span>'
        rows += f"""<tr>
<td>{im.id}</td><td>{im.from_phone}</td><td><a href="/admin/leads/{im.lead_id}">{lead_name}</a></td>
<td style="max-width:300px">{text_preview}</td>
<td>{status_badge}</td><td>{im.received_at or ""}</td>
</tr>"""
    html = f"""<!DOCTYPE html>
<html><head><title>Inbox</title>
<style>table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:6px;text-align:left}}
th{{background:#1f2937;color:#fff}}a{{color:#2563eb}}</style></head><body>
{_MVP_NAV}
<h2>Inbox — Inbound Responses</h2>
<table><tr><th>ID</th><th>From</th><th>Lead</th><th>Message</th><th>Status</th><th>Received</th></tr>
{rows}</table>
</body></html>"""
    return HTMLResponse(content=html)


# ── 5. Settings (MVP) ─────────────────────────────────────────

@admin_router.get("/settings", response_class=HTMLResponse)
def admin_settings(request: Request):
    _require_auth(request)
    html = f"""<!DOCTYPE html>
<html><head><title>MVP Settings</title>
<style>body{{font-family:system-ui;max-width:700px;margin:20px auto;padding:20px}}
.box{{background:#f3f4f6;padding:16px;border-radius:8px;margin:12px 0}}</style></head><body>
{_MVP_NAV}
<h2>MVP Settings</h2>
<div class="box">
<p><b>Environment:</b> {settings.app_env}</p>
<p><b>Collector:</b> {settings.collector_provider}</p>
<p><b>Text Generator:</b> {settings.text_generator_provider}</p>
<p><b>Outreach Provider:</b> {settings.outreach_provider}</p>
<p><b>Outreach Mode:</b> {settings.outreach_mode}</p>
<p><b>Outreach Enabled:</b> {settings.outreach_enabled}</p>
<p><b>WhatsApp Configured:</b> {"Yes" if settings.whatsapp_cloud_api_token else "No (mock only)"}</p>
<p><b>Default Language:</b> {settings.default_language}</p>
</div>
<div class="box">
<p><b>API Docs:</b> <a href="/docs">/docs</a></p>
<p><b>Health:</b> <a href="/health">/health</a></p>
</div>
</body></html>"""
    return HTMLResponse(content=html)
