from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.enrichment.enricher import enrich_lead
from app.models.lead import Lead, LeadStatus
from app.models.search_job import SearchJob, JobStatus
from app.security import log_audit_event


def run_enricher(lead_ids: list[int], job_id: int) -> None:
    db: Session = SessionLocal()
    try:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if not job:
            return

        job.status = JobStatus.enriching.value
        db.commit()

        enriched_ids: list[int] = []
        for lid in lead_ids:
            lead = db.query(Lead).filter(Lead.id == lid).first()
            if not lead:
                continue
            # Each lead is isolated: one lead's enrichment error must not
            # abort the rest of the batch (previously, an unhandled
            # exception here propagated out of the whole loop, silently
            # leaving every subsequent lead un-enriched with no
            # indication anything had gone wrong).
            try:
                result = enrich_lead(lead)
                lead.slug = result["slug"]
                lead.whatsapp = result.get("whatsapp_url")
                lead.phone = result.get("phone") or lead.phone
                lead.status = LeadStatus.enriched.value
                db.commit()
                enriched_ids.append(lead.id)
            except Exception as exc:
                db.rollback()
                lead = db.query(Lead).filter(Lead.id == lid).first()
                if lead:
                    lead.status = LeadStatus.failed.value
                    log_audit_event(
                        db, "enrichment_failed", "lead", str(lead.id),
                        details={"error": str(exc)},
                    )
                    db.commit()

        job.status = JobStatus.generating.value
        db.commit()

    except Exception as exc:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if job:
            job.status = JobStatus.failed.value
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
