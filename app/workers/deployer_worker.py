import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.landing_page import LandingPage, LandingStatus
from app.models.search_job import SearchJob, JobStatus

logger = logging.getLogger(__name__)


def run_deployer(job_id: int) -> None:
    db: Session = SessionLocal()
    try:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if not job:
            return

        import subprocess
        import shutil

        npx = shutil.which("npx")
        if not npx:
            job.status = JobStatus.failed.value
            job.error_message = "npx not found — cannot deploy to Cloudflare"
            db.commit()
            return

        result = subprocess.run(
            [
                npx, "wrangler", "pages", "deploy", "sites/public",
                "--project-name", "leadgen-agent",
                "--branch", "master",
                "--commit-dirty=true",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            job.status = JobStatus.failed.value
            job.error_message = f"Cloudflare deploy failed: {result.stderr[-500:]}"
            db.commit()
            logger.error("Cloudflare deploy failed for job %d: %s", job_id, result.stderr[-200:])
            return

        landings = (
            db.query(LandingPage)
            .filter(LandingPage.status == LandingStatus.published.value)
            .all()
        )
        for landing in landings:
            landing.status = LandingStatus.deployed.value
        db.commit()

        logger.info("Cloudflare deploy completed for job %d", job_id)

    except Exception as exc:
        job = db.query(SearchJob).filter(SearchJob.id == job_id).first()
        if job:
            job.status = JobStatus.failed.value
            job.error_message = f"Deploy error: {exc}"
            db.commit()
        logger.exception("Deployer failed for job %d", job_id)
    finally:
        db.close()
