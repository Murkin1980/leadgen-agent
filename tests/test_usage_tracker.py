import pytest
from app.generation.usage import UsageTracker


class TestUsageTracker:
    def test_estimate_cost_gpt4o_mini(self):
        tracker = UsageTracker()
        cost = tracker._estimate_cost(1000, 500, "gpt-4o-mini")
        expected = (1000 * 0.00015 + 500 * 0.0006) / 1000
        assert abs(cost - expected) < 0.0001

    def test_estimate_cost_gpt4o(self):
        tracker = UsageTracker()
        cost = tracker._estimate_cost(1000, 500, "gpt-4o")
        expected = (1000 * 0.0025 + 500 * 0.01) / 1000
        assert abs(cost - expected) < 0.001

    def test_record_usage(self):
        tracker = UsageTracker()
        tracker._daily_cost = 0
        tracker._daily_date = None
        cost = tracker.record_usage(1000, 500, "gpt-4o-mini")
        assert cost > 0
        assert tracker._daily_cost > 0

    def test_check_daily_budget_within_limit(self):
        tracker = UsageTracker()
        tracker._daily_cost = 0
        tracker._daily_date = None
        assert tracker.check_daily_budget() is True

    def test_check_daily_budget_exceeded(self):
        from datetime import date
        from app.config import settings
        tracker = UsageTracker()
        tracker._daily_date = date.today()
        tracker._daily_cost = settings.openai_daily_budget_usd + 1.0
        assert tracker.check_daily_budget() is False

    def test_get_usage_summary(self):
        tracker = UsageTracker()
        tracker._daily_cost = 0
        tracker._daily_date = None
        summary = tracker.get_usage_summary()
        assert "requests_today" in summary
        assert "input_tokens_today" in summary
        assert "output_tokens_today" in summary
        assert "estimated_cost_usd" in summary
        assert "daily_budget_usd" in summary
        assert "remaining_budget_usd" in summary
        assert summary["remaining_budget_usd"] >= 0
