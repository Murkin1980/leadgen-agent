import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.generation.template import TemplateTextGenerationAdapter
from app.models.landing_page import LandingPage, LandingStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import SearchJob, JobStatus
from app.workers.connection import redis_conn


def run_generator(lead_ids: list[int], job_id: int) -> None:
    db: Session = SessionLocal()
    try:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if not job:
            return

        job.status = JobStatus.generating.value
        db.commit()

        adapter = TemplateTextGenerationAdapter()
        landing_ids: list[str] = []

        for lid in lead_ids:
            lead = db.query(Lead).filter(Lead.id == lid).first()
            if not lead:
                continue

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
            db.flush()
            landing_ids.append(landing_id)

            lead.status = LeadStatus.generated.value

        db.commit()
        job.status = JobStatus.publishing.value
        db.commit()

        if landing_ids:
            from rq import Queue

            q = Queue("publish", connection=redis_conn)
            q.enqueue(
                "app.workers.publisher_worker.run_publisher",
                landing_ids,
                job_id,
            )

    except Exception as exc:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if job:
            job.status = JobStatus.failed.value
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
