import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.deployment.base import DeploymentResult
from app.deployment.cloudflare import CloudflarePagesDeploymentAdapter
from app.deployment.mock import MockDeploymentAdapter
from app.models.deployment import Deployment, DeploymentStatus
from app.models.landing_page import LandingPage, LandingStatus

logger = logging.getLogger(__name__)

SITES_DIR = Path(__file__).resolve().parent.parent.parent / "sites"


def _get_adapter():
    provider = settings.deployment_provider
    if provider == "cloudflare":
        return CloudflarePagesDeploymentAdapter()
    return MockDeploymentAdapter()


def run_deployer(deployment_id: str) -> None:
    db: Session = SessionLocal()
    try:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            logger.error("Deployment %s not found", deployment_id)
            return

        deployment.status = DeploymentStatus.running.value
        deployment.started_at = datetime.now(timezone.utc)
        db.commit()

        adapter = _get_adapter()
        public_dir = SITES_DIR / "public"
        result: DeploymentResult = adapter.deploy(public_dir)

        deployment.stdout_excerpt = result.stdout[:2000] if result.stdout else None
        deployment.stderr_excerpt = result.stderr[:2000] if result.stderr else None

        if result.success:
            deployment.status = DeploymentStatus.succeeded.value
            deployment.deployment_url = result.url
            deployment.provider_deployment_id = result.deployment_id
            deployment.completed_at = datetime.now(timezone.utc)
            db.commit()

            if deployment.job_id:
                landings = (
                    db.query(LandingPage)
                    .join(LandingPage.lead)
                    .filter(
                        LandingPage.status == LandingStatus.published.value,
                        LandingPage.lead.has(search_job_id=deployment.job_id),
                    )
                    .all()
                )
                for landing in landings:
                    landing.status = LandingStatus.deployed.value
                db.commit()

            logger.info("Deployment %s succeeded: %s", deployment_id, result.url)
        else:
            deployment.status = DeploymentStatus.failed.value
            deployment.error_message = result.error
            deployment.completed_at = datetime.now(timezone.utc)
            db.commit()
            logger.error("Deployment %s failed: %s", deployment_id, result.error)

    except Exception as exc:
        try:
            deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
            if deployment:
                deployment.status = DeploymentStatus.failed.value
                deployment.error_message = str(exc)[:2000]
                deployment.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
        logger.exception("Deployer crashed for deployment %s", deployment_id)
    finally:
        db.close()
