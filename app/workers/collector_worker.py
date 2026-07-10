from datetime import datetime, timezone
import logging

from sqlalchemy.orm import Session

from app.collector.factory import create_collector
from app.config import settings
from app.database import SessionLocal
from app.models.lead import Lead, LeadStatus, WebsiteCheckStatus
from app.models.search_job import SearchJob, JobStatus
from app.qualification.service import qualify_lead
from app.verification.website import verify_website
from app.workers.connection import redis_conn

logger = logging.getLogger(__name__)


def _get_collector():
    return create_collector()


def _check_cancellation(db: Session, job_id: int) -> bool:
    """Check if job has been cancelled."""
    job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
    if job and job.status == JobStatus.cancelled.value:
        return True
    return False


def run_collector(job_id: int, provider: str | None = None) -> None:
    db: Session = SessionLocal()
    try:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        job.status = JobStatus.collecting.value
        job.started_at = datetime.now(timezone.utc)
        if provider:
            job.provider = provider
        db.commit()

        collector = _get_collector()
        accepted_count = 0
        page = 1
        page_size = 20

        while accepted_count < job.limit:
            if _check_cancellation(db, job_id):
                logger.info(f"Job {job_id} cancelled")
                job.status = JobStatus.cancelled.value
                db.commit()
                return

            page_result = collector.search_page(
                city=job.city,
                category=job.category,
                page=page,
                page_size=page_size,
            )

            if not page_result.items:
                logger.info(f"No more results at page {page}")
                break

            job.current_page = page
            db.commit()

            for company in page_result.items:
                if accepted_count >= job.limit:
                    break

                if company.website:
                    continue
                if not company.phone:
                    continue
                if not company.name or not company.name.strip():
                    continue

                existing = (
                    db.query(Lead)
                    .filter(Lead.source == job.provider, Lead.source_id == company.source_id)
                    .first()
                )
                if existing:
                    accepted_count += 1
                    continue

                website_check = "pending"
                if settings.verification_enabled and company.website:
                    result = verify_website(company.website)
                    website_check = result["status"]

                lead_data = {
                    "phone": company.phone,
                    "website": company.website,
                    "instagram": company.instagram,
                    "rating": company.rating,
                    "reviews_count": company.reviews_count,
                }
                qual_result = qualify_lead(lead_data)

                lead = Lead(
                    name=company.name,
                    category=company.category,
                    city=company.city,
                    address=company.address,
                    phone=company.phone,
                    whatsapp=company.phone,
                    website=company.website,
                    instagram=company.instagram,
                    source=job.provider,
                    source_id=company.source_id,
                    source_url=company.source_url,
                    rating=company.rating,
                    reviews_count=company.reviews_count,
                    latitude=company.latitude,
                    longitude=company.longitude,
                    has_website=bool(company.website),
                    provider=job.provider,
                    website_check_status=website_check,
                    qualification_score=qual_result.score,
                    qualification_reasons=qual_result.to_json(),
                    status=LeadStatus.collected.value,
                    search_job_id=job_id,
                )
                db.add(lead)
                db.flush()
                accepted_count += 1

            job.processed_count += len(page_result.items)
            job.found_count = job.processed_count
            db.commit()

            if not page_result.has_more:
                break

            page += 1

        job.accepted_count = accepted_count
        job.status = JobStatus.enriching.value
        db.commit()

        lead_ids = [
            lead.id
            for lead in db.query(Lead)
            .filter(Lead.search_job_id == job_id, Lead.status == LeadStatus.collected.value)
            .all()
        ]

        if lead_ids:
            from rq import Queue

            q = Queue("enrich", connection=redis_conn)
            q.enqueue(
                "app.workers.enricher_worker.run_enricher", lead_ids, job_id
            )

    except Exception as exc:
        logger.error(f"Job {job_id} failed: {exc}")
        job.status = JobStatus.failed.value
        job.error_message = str(exc)
        db.commit()
    finally:
        db.close()
