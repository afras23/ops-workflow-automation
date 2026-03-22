"""Performance tests for the ops workflow pipeline.

All tests run with mock AI (zero network latency). The 30-second ceiling
is deliberately generous — it is a regression guard against accidental
synchronous blocking or runaway loops, not a tight SLA test.
"""

from __future__ import annotations

import time
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

_PERF_CEILING_SECONDS = 30.0


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_single_email_processes_within_ceiling(client: TestClient) -> None:
    """A single email completes the full pipeline within 30 seconds (mock AI)."""
    payload = {
        "message_id": "perf_single_1",
        "from": {"name": "Perf Tester", "email": "perf@example.com"},
        "subject": "Performance test email",
        "received_at": "2026-03-22T10:00:00Z",
        "body": (
            "Billing portal error HTTP 500 since Monday morning. "
            "Company: Northwind Traders. All invoices inaccessible."
        ),
    }

    start = time.monotonic()
    response = client.post("/api/v1/ingest", json=payload)
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < _PERF_CEILING_SECONDS, (
        f"Single email took {elapsed:.2f}s — exceeds {_PERF_CEILING_SECONDS}s ceiling"
    )


def test_ten_sequential_emails_within_ceiling(client: TestClient) -> None:
    """Ten sequential ingest calls complete within 30 seconds total (mock AI)."""
    start = time.monotonic()
    for index in range(10):
        response = client.post(
            "/api/v1/ingest",
            json={
                "message_id": f"perf_seq_{index}",
                "from": {"name": "Tester", "email": "tester@example.com"},
                "subject": f"Perf test {index}",
                "received_at": "2026-03-22T10:00:00Z",
                "body": "Please purchase 2 laptops. Item: ThinkPad, Qty: 2.",
            },
        )
        assert response.status_code == 200
    elapsed = time.monotonic() - start

    assert elapsed < _PERF_CEILING_SECONDS, (
        f"10 sequential emails took {elapsed:.2f}s — exceeds {_PERF_CEILING_SECONDS}s ceiling"
    )


def test_health_endpoint_responds_within_one_second(client: TestClient) -> None:
    """The /health liveness endpoint responds in under 1 second."""
    start = time.monotonic()
    response = client.get("/api/v1/health")
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < 1.0, f"/health took {elapsed:.3f}s"


def test_metrics_endpoint_responds_within_two_seconds(client: TestClient) -> None:
    """The /metrics endpoint — which hits the DB — responds in under 2 seconds."""
    start = time.monotonic()
    response = client.get("/api/v1/metrics")
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < 2.0, f"/metrics took {elapsed:.3f}s"
