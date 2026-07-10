from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.collector.mock import MockCollectorAdapter
from app.config import settings
from app.database import SessionLocal
from app.models.lead import Lead, LeadStatus
from app.models.search_job import SearchJob, JobStatus
from app.workers.connection import redis_conn


def run_collector(job_id: int) -> None:
    db: Session = SessionLocal()
    try:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if not job:
            return

        job.status = JobStatus.collecting.value
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        collector = MockCollectorAdapter()
        raw_companies = collector.search(
            city=job.city,
            category=job.category,
            limit=job.limit,
        )

        job.found_count = len(raw_companies)

        accepted_ids: list[int] = []
        for company in raw_companies:
            if company.website:
                continue
            if not company.phone:
                continue
            if not company.name or not company.name.strip():
                continue

            existing = (
                db.query(Lead)
                .filter(Lead.source == "mock", Lead.source_id == company.source_id)
                .first()
            )
            if existing:
                accepted_ids.append(existing.id)
                continue

            lead = Lead(
                name=company.name,
                category=company.category,
                city=company.city,
                address=company.address,
                phone=company.phone,
                website=company.website,
                instagram=company.instagram,
                source="mock",
                source_id=company.source_id,
                source_url=company.source_url,
                rating=company.rating,
                reviews_count=company.reviews_count,
                latitude=company.latitude,
                longitude=company.longitude,
                has_website=bool(company.website),
                status=LeadStatus.collected.value,
            )
            db.add(lead)
            db.flush()
            accepted_ids.append(lead.id)

        job.accepted_count = len(accepted_ids)
        job.status = JobStatus.enriching.value
        db.commit()

        if accepted_ids:
            from rq import Queue

            q = Queue("enrich", connection=redis_conn)
            q.enqueue("app.workers.enricher_worker.run_enricher", accepted_ids, job_id)

    except Exception as exc:
        job.status = JobStatus.failed.value
        job.error_message = str(exc)
        db.commit()
    finally:
        db.close()
