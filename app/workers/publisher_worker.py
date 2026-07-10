import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.landing.renderer import render_landing, save_landing
from app.landing.schema import LandingProfile
from app.models.landing_page import LandingPage, LandingStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import SearchJob, JobStatus
from app.publisher.publisher import publish_site


def run_publisher(landing_ids: list[str], job_id: int) -> None:
    db: Session = SessionLocal()
    try:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if not job:
            return

        job.status = JobStatus.publishing.value
        db.commit()

        for lid in landing_ids:
            landing = db.query(LandingPage).filter(LandingPage.id == lid).first()
            if not landing:
                continue

            try:
                profile_data = json.loads(landing.profile_json)
                profile = LandingProfile(**profile_data)
            except Exception:
                landing.status = LandingStatus.failed.value
                db.commit()
                continue

            try:
                html = render_landing(profile, landing.slug)
                save_landing(landing.slug, html, profile)
                landing.status = LandingStatus.generated.value
                db.commit()
            except Exception:
                landing.status = LandingStatus.failed.value
                db.commit()
                continue

            try:
                preview_url = publish_site(landing.slug)
                landing.preview_url = preview_url
                landing.status = LandingStatus.published.value
                landing.output_path = str(
                    f"sites/public/{landing.slug}"
                )

                lead = db.query(Lead).filter(Lead.id == landing.lead_id).first()
                if lead:
                    lead.status = LeadStatus.published.value

                db.commit()
            except Exception:
                landing.status = LandingStatus.failed.value
                db.commit()

        job.status = JobStatus.completed.value
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as exc:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if job:
            job.status = JobStatus.failed.value
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
