import uuid

import pytest
from app.models.deployment import Deployment, DeploymentStatus
from app.models.landing_page import LandingPage, LandingStatus
from app.models.lead import Lead, LeadStatus
from app.models.search_job import SearchJob, JobStatus


@pytest.fixture()
def job_with_leads_and_landings(db):
    job = SearchJob(
        city="Алматы",
        category="Мебель",
        limit=3,
        status=JobStatus.completed.value,
        found_count=3,
        accepted_count=3,
    )
    db.add(job)
    db.flush()

    suffix = str(uuid.uuid4())[:8]
    leads = []
    for i in range(3):
        lead = Lead(
            name=f"Test Company {i}",
            phone=f"+770011122{i:02d}",
            source="mock",
            source_id=f"own_{suffix}_{i}",
            slug=f"test-company-{suffix}-{i}",
            status=LeadStatus.published.value,
            search_job_id=job.id,
        )
        db.add(lead)
        db.flush()
        leads.append(lead)

    landings = []
    for i, lead in enumerate(leads):
        landing = LandingPage(
            id=str(uuid.uuid4())[:12],
            lead_id=lead.id,
            slug=f"test-company-{suffix}-{i}",
            title=f"Test Company {i}",
            status=LandingStatus.published.value,
        )
        db.add(landing)
        db.flush()
        landings.append(landing)

    db.commit()
    return job, leads, landings


class TestDeploymentOwnership:
    def test_only_job_landings_marked_deployed(self, db, job_with_leads_and_landings):
        job, leads, landings = job_with_leads_and_landings

        other_suffix = str(uuid.uuid4())[:8]
        other_lead = Lead(
            name="Other Company",
            phone="+77009999999",
            source="mock",
            source_id=f"other_{other_suffix}",
            slug=f"other-company-{other_suffix}",
            status=LeadStatus.published.value,
            search_job_id=None,
        )
        db.add(other_lead)
        db.flush()

        other_landing = LandingPage(
            id=str(uuid.uuid4())[:12],
            lead_id=other_lead.id,
            slug=f"other-company-{other_suffix}",
            title="Other Company",
            status=LandingStatus.published.value,
        )
        db.add(other_landing)
        db.commit()

        target_landings = (
            db.query(LandingPage)
            .join(LandingPage.lead)
            .filter(
                LandingPage.status == LandingStatus.published.value,
                Lead.search_job_id == job.id,
            )
            .all()
        )
        assert len(target_landings) == 3

        for landing in target_landings:
            landing.status = LandingStatus.deployed.value
        db.commit()

        other_landing_refreshed = db.query(LandingPage).filter(
            LandingPage.id == other_landing.id
        ).first()
        assert other_landing_refreshed.status == LandingStatus.published.value

    def test_deployment_record_linked_to_job(self, db, job_with_leads_and_landings):
        job, _, _ = job_with_leads_and_landings
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
