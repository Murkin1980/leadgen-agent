import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.deployment import Deployment, DeploymentStatus
from app.models.landing_page import LandingPage, LandingStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import SearchJob, JobStatus
from app.publisher.publisher import publish_site, validate_slug
from app.schemas.deployment import DeploymentResponse
from app.schemas.job import JobCreate, JobResponse
from app.schemas.lead import LeadResponse
from app.schemas.landing import LandingResponse
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
    """List available collector providers."""
    from app.collector.factory import get_available_providers
    return {
        "providers": get_available_providers(),
        "current": settings.collector_provider,
    }


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
    q.enqueue(
        "app.workers.collector_worker.run_collector",
        job.id,
        payload.provider,
    )

    return job


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    """Cancel a running job."""
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in (JobStatus.pending.value, JobStatus.collecting.value):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in status: {job.status}"
        )

    job.status = JobStatus.cancelled.value
    db.commit()
    db.refresh(job)

    return job


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: int, db: Session = Depends(get_db)):
    """Retry a failed job."""
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.failed.value:
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry failed jobs, current status: {job.status}"
        )

    job.status = JobStatus.pending.value
    job.error_message = None
    job.current_page = 0
    job.processed_count = 0
    db.commit()

    from rq import Queue

    q = Queue("collect", connection=redis_conn)
    q.enqueue(
        "app.workers.collector_worker.run_collector",
        job.id,
        job.provider,
    )

    return job


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


@router.post("/leads/{lead_id}/generate", response_model=LandingResponse)
def generate_landing(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    from app.generation.template import TemplateTextGenerationAdapter

    adapter = TemplateTextGenerationAdapter()
    profile_data = adapter.generate_profile(lead)
    landing_id = str(uuid.uuid4())[:12]

    landing = LandingPage(
        id=landing_id,
        lead_id=lead.id,
        slug=lead.slug or "",
        title=profile_data.get("meta", {}).get("title", lead.name),
        profile_json=json.dumps(profile_data, ensure_ascii=False),
        status=LandingStatus.draft.value,
    )
    db.add(landing)
    lead.status = LeadStatus.generated.value
    db.commit()
    db.refresh(landing)

    from rq import Queue

    q = Queue("publish", connection=redis_conn)
    q.enqueue(
        "app.workers.publisher_worker.run_publisher",
        [landing_id],
        lead.search_job_id or 0,
    )

    return landing


@router.post("/landings/{landing_id}/publish", response_model=LandingResponse)
def publish_landing(landing_id: str, db: Session = Depends(get_db)):
    landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
    if not landing:
        raise HTTPException(status_code=404, detail="Landing not found")

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
    landing.output_path = f"sites/public/{landing.slug}"

    lead = db.query(Lead).filter(Lead.id == landing.lead_id).first()
    if lead:
        lead.status = LeadStatus.published.value

    db.commit()
    db.refresh(landing)
    return landing


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
        raise HTTPException(
            status_code=400,
            detail="No published landings to deploy for this job",
        )

    active = (
        db.query(Deployment)
        .filter(
            Deployment.job_id == job_id,
            Deployment.status.in_([
                DeploymentStatus.queued.value,
                DeploymentStatus.running.value,
            ]),
        )
        .count()
    )
    if active > 0:
        raise HTTPException(
            status_code=409,
            detail="An active deployment already exists for this job",
        )

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
