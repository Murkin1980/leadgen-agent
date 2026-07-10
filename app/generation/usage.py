from __future__ import annotations

import json
import logging
from datetime import datetime, date, timezone

from sqlalchemy import func

from app.config import settings
from app.database import SessionLocal
from app.models.content_generation import ContentGeneration, ContentGenerationStatus

logger = logging.getLogger(__name__)


class UsageTracker:
    def __init__(self):
        self._request_counts: dict[str, int] = {}
        self._daily_cost: float = 0.0
        self._daily_date: date | None = None

    def _ensure_today(self) -> None:
        today = date.today()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_cost = 0.0
            self._request_counts.clear()

    def check_job_limit(self, job_id: int) -> bool:
        self._ensure_today()
        db = SessionLocal()
        try:
            count = (
                db.query(func.count(ContentGeneration.id))
                .filter(
                    ContentGeneration.lead_id == job_id,
                    ContentGeneration.status.in_([
                        ContentGenerationStatus.succeeded.value,
                        ContentGenerationStatus.running.value,
                        ContentGenerationStatus.queued.value,
                    ]),
                )
                .scalar()
            )
            return (count or 0) < settings.openai_max_requests_per_job
        finally:
            db.close()

    def check_daily_budget(self) -> bool:
        self._ensure_today()
        return self._daily_cost < settings.openai_daily_budget_usd

    def record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str | None = None,
    ) -> float:
        self._ensure_today()
        cost = self._estimate_cost(input_tokens, output_tokens, model)
        self._daily_cost += cost
        return cost

    def _estimate_cost(
        self, input_tokens: int, output_tokens: int, model: str | None = None
    ) -> float:
        model = model or settings.openai_model
        input_rate = 0.00015
        output_rate = 0.0006
        if "gpt-4o-mini" in model:
            input_rate = 0.00015
            output_rate = 0.0006
        elif "gpt-4o" in model:
            input_rate = 0.0025
            output_rate = 0.01

        return (input_tokens * input_rate + output_tokens * output_rate) / 1000

    def get_usage_summary(self) -> dict:
        self._ensure_today()
        db = SessionLocal()
        try:
            today_start = datetime.combine(date.today(), datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
            stats = (
                db.query(
                    func.count(ContentGeneration.id),
                    func.coalesce(func.sum(ContentGeneration.input_tokens), 0),
                    func.coalesce(func.sum(ContentGeneration.output_tokens), 0),
                    func.coalesce(func.sum(ContentGeneration.estimated_cost_usd), 0),
                )
                .filter(ContentGeneration.created_at >= today_start)
                .one()
            )

            total_requests = stats[0] or 0
            total_input_tokens = int(stats[1] or 0)
            total_output_tokens = int(stats[2] or 0)
            total_cost = float(stats[3] or 0) + self._daily_cost

            return {
                "requests_today": total_requests,
                "input_tokens_today": total_input_tokens,
                "output_tokens_today": total_output_tokens,
                "estimated_cost_usd": round(total_cost, 4),
                "daily_budget_usd": settings.openai_daily_budget_usd,
                "remaining_budget_usd": round(
                    max(0, settings.openai_daily_budget_usd - total_cost), 4
                ),
            }
        finally:
            db.close()


usage_tracker = UsageTracker()
