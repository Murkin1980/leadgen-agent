import json

import pytest

from app.qualification.service import LeadQualifier, QualificationResult, qualify_lead


class TestLeadQualifier:
    def test_qualify_lead_with_phone(self):
        qualifier = LeadQualifier(min_score=0)
        result = qualifier.qualify({"phone": "+77001112233"})
        assert result.score > 0
        assert result.qualified is True

    def test_qualify_lead_without_phone(self):
        qualifier = LeadQualifier(min_score=0)
        result = qualifier.qualify({"phone": None})
        assert result.score == 0

    def test_qualify_lead_with_website_penalty(self):
        qualifier = LeadQualifier(min_score=0)
        result_with = qualifier.qualify({"phone": "+77001112233", "website": "https://example.com"})
        result_without = qualifier.qualify({"phone": "+77001112233", "website": None})
        assert result_with.score < result_without.score

    def test_qualify_lead_with_instagram(self):
        qualifier = LeadQualifier(min_score=0)
        result = qualifier.qualify({"phone": "+77001112233", "instagram": "@test"})
        assert result.score > 0

    def test_qualify_lead_with_good_rating(self):
        qualifier = LeadQualifier(min_score=0)
        result = qualifier.qualify({"phone": "+77001112233", "rating": 4.5})
        assert result.score > 0

    def test_qualify_lead_with_average_rating(self):
        qualifier = LeadQualifier(min_score=0)
        result = qualifier.qualify({"phone": "+77001112233", "rating": 3.5})
        assert result.score > 0

    def test_qualify_lead_with_reviews(self):
        qualifier = LeadQualifier(min_score=0)
        result = qualifier.qualify({"phone": "+77001112233", "reviews_count": 50})
        assert result.score > 0

    def test_qualify_lead_qualified(self):
        qualifier = LeadQualifier(min_score=50)
        result = qualifier.qualify({
            "phone": "+77001112233",
            "instagram": "@test",
            "rating": 4.5,
            "reviews_count": 50,
        })
        assert result.qualified is True
        assert result.score >= 50

    def test_qualify_lead_not_qualified(self):
        qualifier = LeadQualifier(min_score=100)
        result = qualifier.qualify({"phone": "+77001112233"})
        assert result.qualified is False
        assert result.score < 100

    def test_qualify_lead_reasons(self):
        qualifier = LeadQualifier(min_score=0)
        result = qualifier.qualify({
            "phone": "+77001112233",
            "instagram": "@test",
            "rating": 4.5,
            "reviews_count": 50,
        })
        assert len(result.reasons) > 0
        assert any("phone" in r.lower() for r in result.reasons)

    def test_qualification_result_to_json(self):
        result = QualificationResult(score=75, reasons=["test"], qualified=True)
        json_str = result.to_json()
        data = json.loads(json_str)
        assert data["score"] == 75
        assert data["qualified"] is True


class TestQualifyLeadFunction:
    def test_qualify_lead_function(self):
        result = qualify_lead({"phone": "+77001112233"})
        assert isinstance(result, QualificationResult)
        assert result.score > 0

    def test_qualify_lead_empty_data(self):
        result = qualify_lead({})
        assert result.score == 0
        assert result.qualified is False
