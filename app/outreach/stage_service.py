from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.stage import LeadStage, LeadStageHistory
from app.security import log_audit_event

logger = logging.getLogger(__name__)

VALID_TRANSITIONS: dict[str, list[str]] = {
    "new": ["qualified", "do_not_contact"],
    "qualified": ["landing_generated", "do_not_contact"],
    "landing_generated": ["needs_review", "do_not_contact"],
    "needs_review": ["ready_for_outreach", "qualified", "do_not_contact"],
    "ready_for_outreach": ["contacted", "do_not_contact"],
    "contacted": ["replied", "lost", "do_not_contact"],
    "replied": ["interested", "proposal_sent", "won", "lost", "do_not_contact"],
    "interested": ["proposal_sent", "won", "lost", "do_not_contact"],
    "proposal_sent": ["won", "lost", "do_not_contact"],
    "won": [],
    "lost": ["new"],
    "do_not_contact": ["new"],
}


def transition_lead_stage(
    db: Session,
    lead_id: int,
    to_stage: str,
    changed_by: str | None = None,
    reason: str | None = None,
) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise ValueError(f"Lead {lead_id} not found")

    from_stage = lead.stage
    allowed = VALID_TRANSITIONS.get(from_stage, [])
    if to_stage not in allowed:
        raise ValueError(
            f"Invalid transition: {from_stage} -> {to_stage}. "
            f"Allowed: {allowed}"
        )

    lead.stage = to_stage
    history = LeadStageHistory(
        lead_id=lead_id,
        from_stage=from_stage,
        to_stage=to_stage,
        changed_by=changed_by,
        reason=reason,
    )
    db.add(history)

    if to_stage == "do_not_contact":
        lead.do_not_contact = True
    elif from_stage == "do_not_contact" and to_stage == "new":
        lead.do_not_contact = False
        lead.do_not_contact_reason = None

    log_audit_event(
        db, "stage_change", "lead", str(lead_id),
        actor=changed_by,
        details={"from": from_stage, "to": to_stage, "reason": reason},
    )

    db.commit()
    db.refresh(lead)
    return lead
