"""
Regression coverage for GET /readiness.

The endpoint's own docstring promises: "Returns HTTP 503 if any critical
dependency is down." It computed the right status_code but returned a
plain dict, which FastAPI always serializes with HTTP 200 regardless of
the computed value -- so an orchestrator polling this endpoint (its whole
purpose) would never see a failure, even with Postgres or Redis down.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestReadinessStatusCode:
    def test_returns_200_when_all_checks_pass(self, client, db):
        with patch("app.workers.connection.redis_conn.ping", return_value=True):
            response = client.get("/api/v1/readiness")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"

    def test_returns_503_when_a_dependency_is_down(self, client, db):
        with patch("app.workers.connection.redis_conn.ping", side_effect=ConnectionError("down")):
            response = client.get("/api/v1/readiness")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["redis"]["ok"] is False
