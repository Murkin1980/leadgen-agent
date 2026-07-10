"""Prometheus-compatible metrics for observability.

Exposes counters and gauges for queue depth, workers, delivery stats,
webhook deduplication, API latency, DB errors. No PII in labels.
"""
from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import APIRouter, Response


@dataclass
class Counter:
    """Thread-safe counter with optional label set."""

    name: str
    help: str
    value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self.value += amount

    def set(self, value: float) -> None:
        with self._lock:
            self.value = value


@dataclass
class Histogram:
    """Simple histogram for API latency."""

    name: str
    help: str
    _buckets: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def observe(self, value: float) -> None:
        with self._lock:
            key = f"{value:.2f}"
            self._buckets[key] = self._buckets.get(key, 0) + 1

    def sum(self) -> float:
        return sum(float(k) * v for k, v in self._buckets.items())

    def count(self) -> int:
        return sum(self._buckets.values())


# ── Global metric registry ──────────────────────────────────────────

METRICS: dict[str, Counter | Histogram] = {}

queue_depth = Counter("leadgen_queue_depth", "Number of pending jobs in RQ queues")
active_workers = Counter("leadgen_active_workers", "Number of active RQ workers")
messages_sent_total = Counter("leadgen_messages_sent", "Total outbound messages sent", )
messages_delivered_total = Counter("leadgen_messages_delivered", "Messages confirmed delivered")
messages_read_total = Counter("leadgen_messages_read", "Messages confirmed read")
messages_failed_total = Counter("leadgen_messages_failed", "Messages that failed delivery")
messages_retried_total = Counter("leadgen_messages_retried", "Messages retried")
messages_dead_letter_total = Counter("leadgen_messages_dead_letter", "Messages in dead letter queue")
webhook_duplicate_total = Counter("leadgen_webhook_duplicates", "Duplicate webhook events dropped")
webhook_processed_total = Counter("leadgen_webhook_processed", "Webhook events successfully processed")
api_request_latency = Histogram("leadgen_api_request_latency_seconds", "API request latency in seconds")
db_errors_total = Counter("leadgen_db_errors", "Database operation errors")
leads_collected_total = Counter("leadgen_leads_collected", "Total leads collected")
landing_pages_published = Counter("leadgen_landing_pages_published", "Landing pages published")
deployments_total = Counter("leadgen_deployments", "Deployment attempts")

for m in [queue_depth, active_workers, messages_sent_total, messages_delivered_total,
          messages_read_total, messages_failed_total, messages_retried_total,
          messages_dead_letter_total, webhook_duplicate_total, webhook_processed_total,
          api_request_latency, db_errors_total, leads_collected_total,
          landing_pages_published, deployments_total]:
    METRICS[m.name] = m


def record_api_request(duration_seconds: float) -> None:
    """Record API request latency."""
    api_request_latency.observe(duration_seconds)


def record_db_error() -> None:
    """Increment DB error counter."""
    db_errors_total.inc()


def _format_metric(name: str, m: Counter | Histogram) -> str:
    lines = [f"# HELP {m.help}", f"# TYPE {name} gauge" if isinstance(m, Counter) else f"# TYPE {name} summary"]
    if isinstance(m, Counter):
        lines.append(f"{name} {m.value}")
    elif isinstance(m, Histogram):
        lines.append(f"{name}_count {m.count()}")
        lines.append(f"{name}_sum {m.sum():.6f}")
    return "\n".join(lines)


def metrics_text() -> str:
    """Return Prometheus text exposition format."""
    parts = []
    for name, m in METRICS.items():
        parts.append(_format_metric(name, m))
    return "\n".join(parts) + "\n"


metrics_router = APIRouter()


@metrics_router.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(content=metrics_text(), media_type="text/plain; version=0.0.4; charset=utf-8")
