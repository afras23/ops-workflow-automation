"""Integration tests for observability features.

Tests:
- test_correlation_id_in_response_header   — every response carries X-Correlation-ID
- test_metrics_returns_real_data           — /metrics reflects ingested items
- test_health_ready_reports_database_status — /health/ready checks storage + AI provider

All tests use the autouse _isolate_test_db fixture (conftest.py) which sets
AI_PROVIDER=mock and redirects storage to a per-test tmp_path directory.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Yield a TestClient that triggers the FastAPI lifespan."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ingest(client: TestClient, message_id: str, subject: str = "Billing portal error") -> dict:
    """Ingest a single email and return the response JSON.

    Args:
        client: TestClient to POST against.
        message_id: Unique message identifier.
        subject: Controls MockAIClient routing via keyword matching.

    Returns:
        Parsed response JSON dict.
    """
    response = client.post(
        "/api/v1/ingest",
        json={
            "message_id": message_id,
            "from": {"name": "Test User", "email": "user@example.com"},
            "subject": subject,
            "received_at": "2026-03-22T10:00:00Z",
            "body": (
                "Billing error on the portal. Company: Northwind Traders. "
                "HTTP 500 on every page load since this morning."
            ),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_correlation_id_in_response_header(client: TestClient) -> None:
    """Every response includes a non-empty X-Correlation-ID header."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    cid = response.headers.get("x-correlation-id")
    assert cid, "X-Correlation-ID header must be present and non-empty"


def test_provided_correlation_id_is_echoed(client: TestClient) -> None:
    """A caller-supplied X-Correlation-ID is returned unchanged."""
    custom_cid = "trace-abc-123"
    response = client.get("/api/v1/health", headers={"X-Correlation-ID": custom_cid})
    assert response.status_code == 200
    assert response.headers.get("x-correlation-id") == custom_cid


def test_metrics_returns_real_data(client: TestClient) -> None:
    """After ingesting items, /metrics reflects the real DB counts."""
    # Ingest two items so metrics are non-trivial
    _ingest(client, "obs_msg_1")
    _ingest(client, "obs_msg_2")

    response = client.get("/api/v1/metrics")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"

    data = body["data"]
    # Required keys
    for key in (
        "processed_today",
        "success_rate",
        "avg_latency_ms",
        "avg_cost_usd",
        "cost_today_usd",
        "cost_limit_usd",
        "queue_depth",
        "items",
    ):
        assert key in data, f"Missing metrics key: {key}"

    # At least 2 items processed today
    assert data["processed_today"] >= 2

    # cost_limit_usd reflects the configured ceiling
    assert data["cost_limit_usd"] > 0

    # Sanity: success_rate is a valid fraction
    assert 0.0 <= data["success_rate"] <= 1.0

    # metadata must include correlation_id
    assert "correlation_id" in body["metadata"]
    assert body["metadata"]["correlation_id"]  # non-empty (set by middleware)


def test_health_ready_reports_database_status(client: TestClient) -> None:
    """GET /health/ready returns ready status with storage and ai_provider checks."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ready"
    assert "checks" in body

    checks = body["checks"]
    assert checks["storage"] == "ok"
    assert checks["ai_provider"] == "ok"  # mock provider is always ok
