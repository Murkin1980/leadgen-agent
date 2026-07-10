from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.landing_page import (
    ChangeSource,
    LandingPage,
    LandingPageVersion,
    LandingStatus,
    ReviewStatus,
)
from app.models.lead import Lead
from app.models.content_generation import ContentGeneration

admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _check_auth(request: Request) -> bool:
    auth = request.cookies.get("admin_auth")
    if not auth:
        return False
    return secrets.compare_digest(auth, settings.admin_password)


def _require_auth(request: Request):
    if not _check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


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
    resp = RedirectResponse(url="/admin/landings", status_code=302)
    resp.set_cookie("admin_auth", password, httponly=True, max_age=3600)
    return resp


@admin_router.get("/leads", response_class=HTMLResponse)
def admin_leads(request: Request, db: Session = Depends(get_db)):
    _require_auth(request)
    leads = db.query(Lead).order_by(Lead.id.desc()).limit(100).all()
    rows = ""
    for l in leads:
        rows += f"""<tr>
<td>{l.id}</td><td>{l.name}</td><td>{l.city}</td><td>{l.phone}</td>
<td>{l.qualification_score}</td><td>{l.status}</td>
<td><a href="/admin/landings?lead_id={l.id}">landings</a></td>
</tr>"""
    html = f"""<!DOCTYPE html>
<html><head><title>Leads</title>
<style>table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#1f2937;color:#fff}}a{{color:#2563eb}}</style></head><body>
<h2>Leads</h2>
<table><tr><th>ID</th><th>Name</th><th>City</th><th>Phone</th><th>Score</th><th>Status</th><th>Actions</th></tr>
{rows}</table>
</body></html>"""
    return HTMLResponse(content=html)


@admin_router.get("/landings", response_class=HTMLResponse)
def admin_landings(request: Request, lead_id: int | None = None, db: Session = Depends(get_db)):
    _require_auth(request)
    q = db.query(LandingPage).order_by(LandingPage.id.desc())
    if lead_id:
        q = q.filter(LandingPage.lead_id == lead_id)
    landings = q.limit(100).all()
    rows = ""
    for lp in landings:
        rows += f"""<tr>
<td>{lp.id}</td><td>{lp.lead_id}</td><td>{lp.slug}</td>
<td>{lp.review_status}</td><td>{lp.status}</td><td>v{lp.current_version}</td>
<td><a href="/admin/landings/{lp.id}">review</a></td>
</tr>"""
    html = f"""<!DOCTYPE html>
<html><head><title>Landings</title>
<style>table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#1f2937;color:#fff}}a{{color:#2563eb}}</style></head><body>
<h2>Landings</h2>
<table><tr><th>ID</th><th>Lead</th><th>Slug</th><th>Review</th><th>Status</th><th>Version</th><th>Actions</th></tr>
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
    gen = None
    if lp.generation_id:
        gen = db.query(ContentGeneration).filter(ContentGeneration.id == lp.generation_id).first()
    versions = (
        db.query(LandingPageVersion)
        .filter(LandingPageVersion.landing_page_id == landing_id)
        .order_by(LandingPageVersion.version_number.desc())
        .all()
    )

    profile_data = {}
    if lp.profile_json:
        try:
            profile_data = json.loads(lp.profile_json)
        except (json.JSONDecodeError, AttributeError):
            pass

    validation_info = ""
    if gen and gen.validation_errors_json:
        try:
            ve = json.loads(gen.validation_errors_json)
            validation_info = f"Errors: {ve.get('errors', [])}<br>Warnings: {ve.get('warnings', [])}"
        except (json.JSONDecodeError, AttributeError):
            pass

    gen_info = ""
    if gen:
        gen_info = f"<p>Provider: {gen.provider} | Model: {gen.model or 'n/a'} | Status: {gen.status}</p>"

    lead_info = ""
    if lead:
        lead_info = f"""<p><b>Lead:</b> {lead.name} | City: {lead.city} | Phone: {lead.phone} | Score: {lead.qualification_score}</p>"""

    versions_html = ""
    for v in versions:
        versions_html += f"<li>v{v.version_number} — {v.change_source} — {v.change_note or ''}</li>"

    preview = ""
    if lp.preview_url:
        preview = f'<iframe src="{lp.preview_url}" width="100%" height="600" frameborder="0"></iframe>'

    html = f"""<!DOCTYPE html>
<html><head><title>Landing {landing_id}</title>
<style>body{{font-family:system-ui;max-width:900px;margin:20px auto;padding:20px}}
.box{{background:#f3f4f6;padding:16px;border-radius:8px;margin:12px 0}}
.btn{{padding:8px 16px;border:none;border-radius:6px;cursor:pointer;margin:4px}}
.btn-approve{{background:#16a34a;color:#fff}}
.btn-reject{{background:#dc2626;color:#fff}}
.btn-edit{{background:#2563eb;color:#fff}}</style></head><body>
<h2>Landing {landing_id}</h2>
{lead_info}
{gen_info}
<div class="box"><b>Review status:</b> {lp.review_status} | <b>Status:</b> {lp.status} | <b>Version:</b> v{lp.current_version}</div>
<div class="box"><b>Validation:</b><br>{validation_info or 'No validation data'}</div>
<div class="box"><b>Versions:</b><ul>{versions_html or '<li>No versions</li>'}</ul></div>
<form method="post" action="/admin/landings/{landing_id}/approve" style="display:inline">
<button class="btn btn-approve" type="submit">Approve</button></form>
<form method="post" action="/admin/landings/{landing_id}/reject" style="display:inline">
<input name="reason" placeholder="Reason" value="Не подходит">
<button class="btn btn-reject" type="submit">Reject</button></form>
{preview}
</body></html>"""
    return HTMLResponse(content=html)


@admin_router.post("/landings/{landing_id}/approve")
def admin_approve_landing(
    landing_id: str, request: Request, db: Session = Depends(get_db)
):
    _require_auth(request)
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
    landing_id: str, request: Request, reason: str = Form("Не подходит"), db: Session = Depends(get_db)
):
    _require_auth(request)
    lp = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Landing not found")
    lp.review_status = ReviewStatus.rejected.value
    lp.status = LandingStatus.failed.value
    lp.review_note = reason
    db.commit()
    return RedirectResponse(url=f"/admin/landings/{landing_id}", status_code=302)


@admin_router.get("/generations/{generation_id}", response_class=HTMLResponse)
def admin_generation_detail(
    generation_id: str, request: Request, db: Session = Depends(get_db)
):
    _require_auth(request)
    gen = db.query(ContentGeneration).filter(ContentGeneration.id == generation_id).first()
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")

    output_pretty = ""
    if gen.output_json:
        try:
            output_pretty = json.dumps(json.loads(gen.output_json), indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, AttributeError):
            output_pretty = gen.output_json

    validation_pretty = ""
    if gen.validation_errors_json:
        try:
            validation_pretty = json.dumps(json.loads(gen.validation_errors_json), indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, AttributeError):
            validation_pretty = gen.validation_errors_json

    html = f"""<!DOCTYPE html>
<html><head><title>Generation {generation_id}</title>
<style>body{{font-family:system-ui;max-width:900px;margin:20px auto;padding:20px}}
pre{{background:#f3f4f6;padding:16px;border-radius:8px;overflow-x:auto}}
.box{{background:#f3f4f6;padding:16px;border-radius:8px;margin:12px 0}}</style></head><body>
<h2>Generation {generation_id}</h2>
<div class="box">
<p><b>Lead ID:</b> {gen.lead_id} | <b>Provider:</b> {gen.provider} | <b>Model:</b> {gen.model or 'n/a'}</p>
<p><b>Status:</b> {gen.status} | <b>Language:</b> {gen.language}</p>
<p><b>Prompt version:</b> {gen.prompt_version} | <b>Tokens:</b> in={gen.input_tokens or 0} out={gen.output_tokens or 0}</p>
<p><b>Cost:</b> ${gen.estimated_cost_usd or 0:.4f}</p>
</div>
<h3>Output</h3>
<pre>{output_pretty or 'No output'}</pre>
<h3>Validation</h3>
<pre>{validation_pretty or 'No validation data'}</pre>
</body></html>"""
    return HTMLResponse(content=html)
