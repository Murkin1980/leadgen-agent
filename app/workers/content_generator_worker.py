import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.generation.base import GeneratedProfile
from app.generation.context import GenerationContext
from app.generation.factory import create_text_generator
from app.generation.validator import GeneratedContentValidator
from app.models.content_generation import ContentGeneration, ContentGenerationStatus
from app.models.landing_page import (
    ChangeSource,
    LandingPage,
    LandingPageVersion,
    LandingStatus,
    ReviewStatus,
)
from app.models.lead import Lead, LeadStatus
from app.workers.connection import redis_conn

logger = logging.getLogger(__name__)


def run_content_generator(generation_id: str) -> None:
    db: Session = SessionLocal()
    try:
        gen = db.query(ContentGeneration).filter(ContentGeneration.id == generation_id).first()
        if not gen:
            logger.error("ContentGeneration %s not found", generation_id)
            return

        gen.status = ContentGenerationStatus.running.value
        gen.started_at = datetime.now(timezone.utc)
        db.commit()

        lead = db.query(Lead).filter(Lead.id == gen.lead_id).first()
        if not lead:
            gen.status = ContentGenerationStatus.failed.value
            gen.error_message = f"Lead {gen.lead_id} not found"
            gen.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        qual_reasons = []
        if lead.qualification_reasons:
            try:
                qual_data = json.loads(lead.qualification_reasons)
                qual_reasons = qual_data.get("reasons", [])
            except (json.JSONDecodeError, AttributeError):
                pass

        context = GenerationContext.from_lead(lead, qualification_reasons=qual_reasons)
        context.language = gen.language or "ru"
        context.notes = gen.notes

        gen.input_snapshot_json = json.dumps(
            {
                "company_name": context.company_name,
                "city": context.city,
                "category": context.category,
                "phone": context.phone,
                "language": context.language,
            },
            ensure_ascii=False,
        )
        db.commit()

        provider = gen.provider
        adapter = create_text_generator(provider)

        try:
            profile: GeneratedProfile = adapter.generate(context)
        except Exception as e:
            gen.status = ContentGenerationStatus.failed.value
            gen.error_message = str(e)[:2000]
            gen.completed_at = datetime.now(timezone.utc)
            db.commit()
            logger.error("Generation %s failed: %s", generation_id, e)
            return

        validator = GeneratedContentValidator()
        validation_result = validator.validate(profile, context)

        gen.output_json = json.dumps(profile.to_dict(), ensure_ascii=False)
        gen.validation_errors_json = validation_result.to_json()

        if not validation_result.is_valid:
            gen.status = ContentGenerationStatus.rejected.value
            gen.completed_at = datetime.now(timezone.utc)
            db.commit()
            logger.warning(
                "Generation %s rejected: %s",
                generation_id,
                validation_result.errors,
            )
            return

        gen.status = ContentGenerationStatus.succeeded.value
        gen.completed_at = datetime.now(timezone.utc)

        landing_id = gen.landing_page_id
        if not landing_id:
            landing_id = str(uuid.uuid4())[:12]
            gen.landing_page_id = landing_id

        landing = db.query(LandingPage).filter(LandingPage.id == landing_id).first()
        if not landing:
            landing = LandingPage(
                id=landing_id,
                lead_id=lead.id,
                slug=lead.slug or "",
                title=profile.data.get("meta", {}).get("title", lead.name),
                profile_json=json.dumps(profile.data, ensure_ascii=False),
                status=LandingStatus.draft.value,
                review_status=ReviewStatus.needs_review.value,
                generation_id=generation_id,
            )
            db.add(landing)
        else:
            landing.profile_json = json.dumps(profile.data, ensure_ascii=False)
            landing.title = profile.data.get("meta", {}).get("title", lead.name)
            landing.review_status = ReviewStatus.needs_review.value
            landing.generation_id = generation_id

        db.flush()

        version_number = (landing.current_version or 0) + 1
        version = LandingPageVersion(
            id=str(uuid.uuid4())[:12],
            landing_page_id=landing_id,
            version_number=version_number,
            profile_json=json.dumps(profile.data, ensure_ascii=False),
            change_source=ChangeSource.openai.value if provider == "openai" else ChangeSource.template.value,
            change_note=f"Generated by {provider}",
        )
        db.add(version)
        landing.current_version = version_number

        db.commit()

        logger.info(
            "Generation %s succeeded, landing %s at version %d",
            generation_id,
            landing_id,
            version_number,
        )

    except Exception as exc:
        logger.exception("Content generator worker crashed for %s", generation_id)
        try:
            gen = db.query(ContentGeneration).filter(ContentGeneration.id == generation_id).first()
            if gen:
                gen.status = ContentGenerationStatus.failed.value
                gen.error_message = str(exc)[:2000]
                gen.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
