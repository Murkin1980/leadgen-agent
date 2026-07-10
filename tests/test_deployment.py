import uuid
from datetime import datetime, timezone

import pytest
from app.models.deployment import Deployment, DeploymentStatus
from app.models.landing_page import LandingPage, LandingStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import SearchJob, JobStatus
from app.workers.connection import redis_conn


class TestDeploymentModel:
    def test_create_deployment(self, db):
        deployment = Deployment(
            id=str(uuid.uuid4())[:12],
            provider="mock",
            status=DeploymentStatus.queued.value,
            project_name="test-project",
            branch="master",
        )
        db.add(deployment)
        db.commit()
        db.refresh(deployment)
        assert deployment.id
        assert deployment.status == "queued"
        assert deployment.provider == "mock"

    def test_deployment_with_job(self, db):
        job = SearchJob(city="Алматы", category="Мебель", status=JobStatus.completed.value)
        db.add(job)
        db.flush()

        deployment = Deployment(
            id=str(uuid.uuid4())[:12],
            job_id=job.id,
            provider="mock",
            status=DeploymentStatus.queued.value,
        )
        db.add(deployment)
        db.commit()
        db.refresh(deployment)
        assert deployment.job_id == job.id

    def test_deployment_status_transitions(self, db):
        deployment = Deployment(
            id=str(uuid.uuid4())[:12],
            provider="mock",
            status=DeploymentStatus.queued.value,
        )
        db.add(deployment)
        db.commit()

        deployment.status = DeploymentStatus.running.value
        deployment.started_at = datetime.now(timezone.utc)
        db.commit()

        deployment.status = DeploymentStatus.succeeded.value
        deployment.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(deployment)
        assert deployment.status == "succeeded"


class TestDeploymentStatusValues:
    def test_all_statuses(self):
        assert DeploymentStatus.queued.value == "queued"
        assert DeploymentStatus.running.value == "running"
        assert DeploymentStatus.succeeded.value == "succeeded"
        assert DeploymentStatus.failed.value == "failed"
