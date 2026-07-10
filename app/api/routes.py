import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from rq import Queue
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.generation.context import GenerationContext
from app.generation.factory import create_text_generator, get_available_text_providers
from app.generation.usage import usage_tracker
from app.generation.validator import GeneratedContentValidator
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.deployment import Deployment, DeploymentStatus
from app.models.landing_page import (
    ChangeSource,
    LandingPage,
    LandingPageVersion,
    LandingStatus,
    ReviewStatus,
)
from app.models.lead import Lead, LeadStatus
from app.models.search_job import SearchJob, JobStatus
from app.publisher.publisher import publish_site, validate_slug
from app.schemas.content_generation import ContentGenerationCreate, ContentGenerationResponse
from app.schemas.deployment import DeploymentResponse
from app.schemas.job import JobCreate, JobResponse
from app.schemas.landing import (
    LandingApproveRequest,
    LandingRejectRequest,
    LandingResponse,
    LandingVersionResponse,
)
from app.schemas.lead import LeadResponse
from app.workers.connection import redis_conn

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health_check():
    pg_ok = True
    redis_ok = True
    try:
        from app.database import engine
        import sqlalchemy

        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
    except Exception:
        pg_ok = False
    try:
        redis_conn.ping()
    except Exception:
        redis_ok = False

    status = "ok" if pg_ok and redis_ok else "degraded"
    return {"status": status, "postgres": pg_ok, "redis": redis_ok}


@router.get("/providers")
def list_providers():
    from app.collector.factory import get_available_providers
    return {
        "collector_providers": get_available_providers(),
        "text_generator_providers": get_available_text_providers(),
        "current_collector": settings.collector_provider,
        "current_generator": settings.text_generator_provider,
    }


# --- Jobs ---

@router.post("/jobs", response_model=JobResponse)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = SearchJob(
        city=payload.city,
        category=payload.category,
        limit=payload.limit,
        provider=payload.provider,
        status=JobStatus.pending.value,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    from rq import Queue
    q = Queue("collect", connection=redis_conn)
    q.enqueue("app.workers.collector_worker.run_collector", job.id, payload.provider)
    return job


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.pending.value, JobStatus.collecting.value):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job in status: {job.status}")
    job.status = JobStatus.cancelled.value
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.failed.value:
        raise HTTPException(status_code=400, detail=f"Can only retry failed jobs, current status: {job.status}")
    job.status = JobStatus.pending.value
    job.error_message = None
    job.current_page = 0
    job.processed_count = 0
    db.commit()
    from rq import Queue
    q = Queue("collect", connection=redis_conn)
    q.enqueue("app.workers.collector_worker.run_collector", job.id, job.provider)
    return job


# --- Leads ---

@router.get("/leads", response_model=list[LeadResponse])
def list_leads(
    city: str | None = None,
    category: str | None = None,
    status: str | None = None,
    has_website: bool | None = None,
    provider: str | None = None,
    search_job_id: int | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Lead)
    if city:
        q = q.filter(Lead.city == city)
    if category:
        q = q.filter(Lead.category == category)
    if status:
        q = q.filter(Lead.status == status)
    if has_website is not None:
        q = q.filter(Lead.has_website == has_website)
    if provider:
        q = q.filter(Lead.provider == provider)
    if search_job_id is not None:
        q = q.filter(Lead.search_job_id == search_job_id)
    return q.order_by(Lead.id.desc()).offset(offset).limit(limit).all()


@router.get("/leads/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


# --- Content Generations ---

@router.post("/leads/{lead_id}/content-generations", response_model=ContentGenerationResponse)
def create_content_generation(
    lead_id: int,
    payload: ContentGenerationCreate | None = None,
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    provider = (payload.provider if payload else None) or settings.text_generator_provider
    language = (payload.language if payload else None) or settings.default_language
    notes = (payload.notes if payload else None) or None

    generation_id = str(uuid.uuid4())[:12]
    gen = ContentGeneration(
        id=generation_id,
        lead_id=lead_id,
        provider=provider,
        model=settings.openai_model if provider == "openai" else None,
        prompt_version="v1",
        status=ContentGenerationStatus.queued.value,
        language=language,
        notes=notes,
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)

    q = Queue("generate_content", connection=redis_conn)
    q.enqueue("app.workers.content_generator_worker.run_content_generator", generation_id)

    return gen


@router.get("/content-generations", response_model=list[ContentGenerationResponse])
def list_content_generations(
    lead_id: int | None = None,
    status: str | None = None,
    provider: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(ContentGeneration)
    if lead_id is not None:
        q = q.filter(ContentGeneration.lead_id == lead_id)
    if status:
        q = q.filter(ContentGeneration.status == status)
    if provider:
        q = q.filter(ContentGeneration.provider == provider)
    return q.order_by(ContentGeneration.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/content-generations/{generation_id}", response_model=ContentGenerationResponse)
def get_content_generation(generation_id: str, db: Session = Depends(get_db)):
    gen = db.query(ContentGeneration).filter(ContentGeneration.id == generation_id).first()
    if not gen:
        raise HTTPException(status_code=404, detail="Content generation not found")
    return gen


# --- Landing review ---

@router.get("/landings", response_model=list[LandingResponse])
def list_landings(
    lead_id: int | None = None,
    review_status: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(LandingPage)
    if lead_id is not None:
        q = q.filter(LandingPage.lead_id == lead_id)
    if review_status:
        q = q.filter(LandingPage.review_status == review_status)
    return q.order_by(LandingPage.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/landings/{landing_id}", response_model=LandingResponse)
def get_landing(landing_id: str, db: Session = Depends(get_db)):
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")
    return landing


@router.post("/landings/{landing_id}/approve", response_model=LandingResponse)
def approve_landing(landing_id: str, payload: LandingApproveRequest | None = None, db: Session = Depends(get_db)):
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")

    from datetime import datetime, timezone
    landing.review_status = ReviewStatus.approved.value
    landing.status = LandingStatus.approved.value
    landing.approved_at = datetime.now(timezone.utc)
    landing.approved_by = (payload.approved_by if payload else "api") or "api"
    db.commit()
    db.refresh(landing)
    return landing


@router.post("/landings/{landing_id}/reject", response_model=LandingResponse)
def reject_landing(landing_id: str, payload: LandingRejectRequest | None = None, db: Session = Depends(get_db)):
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")

    landing.review_status = ReviewStatus.rejected.value
    landing.status = LandingStatus.failed.value
    landing.review_note = (payload.reason if payload else "Rejected via API") or "Rejected via API"
    db.commit()
    db.refresh(landing)
    return landing


@router.put("/landings/{landing_id}/profile", response_model=LandingResponse)
def update_landing_profile(landing_id: str, profile_data: dict, db: Session = Depends(get_db)):
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")

    from app.landing.schema import LandingProfile
    try:
        LandingProfile(**profile_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid profile: {e}")

    landing.profile_json = json.dumps(profile_data, ensure_ascii=False)
    landing.review_status = ReviewStatus.needs_review.value
    version_number = (landing.current_version or 0) + 1
    version = LandingPageVersion(
        id=str(uuid.uuid4())[:12],
        landing_page_id=landing_id,
        version_number=version_number,
        profile_json=json.dumps(profile_data, ensure_ascii=False),
        change_source=ChangeSource.manual.value,
        change_note="Manual edit via API",
    )
    db.add(version)
    landing.current_version = version_number
    db.commit()
    db.refresh(landing)
    return landing


@router.get("/landings/{landing_id}/versions", response_model=list[LandingVersionResponse])
def list_landing_versions(landing_id: str, db: Session = Depends(get_db)):
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")
    return (
        db.query(LandingPageVersion)
        .filter(LandingPageVersion.landing_page_id == landing_id)
        .order_by(LandingPageVersion.version_number.desc())
        .all()
    )


@router.get("/landings/{landing_id}/versions/{version_number}", response_model=LandingVersionResponse)
def get_landing_version(landing_id: str, version_number: int, db: Session = Depends(get_db)):
    v = (
        db.query(LandingPageVersion)
        .filter(
            LandingPageVersion.landing_page_id == landing_id,
            LandingPageVersion.version_number == version_number,
        )
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    return v


@router.post("/landings/{landing_id}/versions/{version_number}/restore", response_model=LandingResponse)
def restore_landing_version(landing_id: str, version_number: int, db: Session = Depends(get_db)):
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")
    v = (
        db.query(LandingPageVersion)
        .filter(
            LandingPageVersion.landing_page_id == landing_id,
            LandingPageVersion.version_number == version_number,
        )
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")

    landing.profile_json = v.profile_json
    landing.review_status = ReviewStatus.needs_review.value
    new_version_number = (landing.current_version or 0) + 1
    new_version = LandingPageVersion(
        id=str(uuid.uuid4())[:12],
        landing_page_id=landing_id,
        version_number=new_version_number,
        profile_json=v.profile_json,
        change_source=ChangeSource.manual.value,
        change_note=f"Restored from v{version_number}",
    )
    db.add(new_version)
    landing.current_version = new_version_number
    db.commit()
    db.refresh(landing)
    return landing


# --- Publish ---

@router.post("/landings/{landing_id}/publish", response_model=LandingResponse)
def publish_landing(landing_id: str, db: Session = Depends(get_db)):
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")

    if landing.review_status != ReviewStatus.approved.value:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot publish landing in review_status={landing.review_status}. Must be 'approved'.",
        )

    from app.landing.renderer import render_landing, save_landing
    from app.landing.schema import LandingProfile

    try:
        profile_data = json.loads(landing.profile_json)
        profile = LandingProfile(**profile_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid profile: {e}")

    try:
        validate_slug(landing.slug)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    html = render_landing(profile, landing.slug)
    save_landing(landing.slug, html, profile)
    preview_url = publish_site(landing.slug)

    landing.preview_url = preview_url
    landing.status = LandingStatus.published.value
    landing.review_status = ReviewStatus.published.value
    landing.output_path = f"sites/public/{landing.slug}"

    lead = db.query(Lead).filter(Lead.id == landing.lead_id).first()
    if lead:
        lead.status = LeadStatus.published.value

    db.commit()
    db.refresh(landing)
    return landing


# --- Deploy ---

@router.post("/jobs/{job_id}/deploy", response_model=DeploymentResponse)
def deploy_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    published = (
        db.query(LandingPage)
        .join(LandingPage.lead)
        .filter(
            LandingPage.status == LandingStatus.published.value,
            Lead.search_job_id == job_id,
        )
        .count()
    )
    if published == 0:
        raise HTTPException(status_code=400, detail="No published landings to deploy for this job")

    active = (
        db.query(Deployment)
        .filter(
            Deployment.job_id == job_id,
            Deployment.status.in_([DeploymentStatus.queued.value, DeploymentStatus.running.value]),
        )
        .count()
    )
    if active > 0:
        raise HTTPException(status_code=409, detail="An active deployment already exists for this job")

    deployment = Deployment(
        id=str(uuid.uuid4())[:12],
        job_id=job_id,
        provider=settings.deployment_provider,
        project_name=settings.cloudflare_pages_project,
        branch=settings.cloudflare_pages_branch,
        status=DeploymentStatus.queued.value,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    from rq import Queue
    q = Queue("deploy", connection=redis_conn)
    q.enqueue("app.workers.deployer_worker.run_deployer", deployment.id)
    return deployment


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(deployment_id: str, db: Session = Depends(get_db)):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.get("/deployments", response_model=list[DeploymentResponse])
def list_deployments(
    job_id: int | None = None,
    status: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Deployment)
    if job_id is not None:
        q = q.filter(Deployment.job_id == job_id)
    if status:
        q = q.filter(Deployment.status == status)
    return q.order_by(Deployment.created_at.desc()).offset(offset).limit(limit).all()


# --- Usage ---

@router.get("/usage/openai")
def get_openai_usage():
    return usage_tracker.get_usage_summary()
