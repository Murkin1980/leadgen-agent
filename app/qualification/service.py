from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class QualificationResult:
    """Result of lead qualification scoring."""
    score: int
    reasons: list[str]
    qualified: bool

    def to_json(self) -> str:
        """Serialize to JSON string for storage."""
        import json
        return json.dumps({
            "score": self.score,
            "reasons": self.reasons,
            "qualified": self.qualified,
        }, ensure_ascii=False)


class LeadQualifier:
    """Qualifies leads based on scoring rules."""

    def __init__(
        self,
        min_score: int | None = None,
        score_phone: int | None = None,
        score_website: int | None = None,
        score_instagram: int | None = None,
        score_rating: int | None = None,
        score_reviews: int | None = None,
    ):
        self.min_score = min_score if min_score is not None else settings.lead_min_score
        self.score_phone = score_phone if score_phone is not None else settings.lead_score_phone
        self.score_website = score_website if score_website is not None else settings.lead_score_website
        self.score_instagram = score_instagram if score_instagram is not None else settings.lead_score_instagram
        self.score_rating = score_rating if score_rating is not None else settings.lead_score_rating
        self.score_reviews = score_reviews if score_reviews is not None else settings.lead_score_reviews

    def qualify(self, lead_data: dict) -> QualificationResult:
        """
        Qualify a lead based on its data.
        
        Args:
            lead_data: Dict with lead fields (phone, website, instagram, rating, reviews_count, etc.)
            
        Returns:
            QualificationResult with score, reasons, and qualified status
        """
        score = 0
        reasons = []

        phone = lead_data.get("phone")
        if phone:
            score += self.score_phone
            reasons.append(f"Has phone: +{self.score_phone}")
        else:
            reasons.append("No phone")

        website = lead_data.get("website")
        if website:
            score += self.score_website
            reasons.append(f"Has website: {self.score_website}")
        else:
            reasons.append("No website (good for landing)")

        instagram = lead_data.get("instagram")
        if instagram:
            score += self.score_instagram
            reasons.append(f"Has Instagram: +{self.score_instagram}")

        rating = lead_data.get("rating")
        if rating and rating >= 4.0:
            score += self.score_rating
            reasons.append(f"Good rating ({rating}): +{self.score_rating}")
        elif rating and rating >= 3.0:
            score += self.score_rating // 2
            reasons.append(f"Average rating ({rating}): +{self.score_rating // 2}")

        reviews_count = lead_data.get("reviews_count")
        if reviews_count and reviews_count >= 10:
            score += self.score_reviews
            reasons.append(f"Has reviews ({reviews_count}): +{self.score_reviews}")

        qualified = score >= self.min_score
        reasons.append(f"Total score: {score} (min: {self.min_score})")

        return QualificationResult(
            score=score,
            reasons=reasons,
            qualified=qualified,
        )


def qualify_lead(lead_data: dict) -> QualificationResult:
    """Convenience function to qualify a lead."""
    qualifier = LeadQualifier()
    return qualifier.qualify(lead_data)
