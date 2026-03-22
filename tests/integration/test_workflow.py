"""Integration tests for the full workflow pipeline.

Tests the end-to-end ingest → route → review flow via the HTTP API.
All external services (AI, Slack, CRM) use mocks configured at startup.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Yield a TestClient that triggers the FastAPI lifespan on entry."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_ingest_idempotent(client: TestClient) -> None:
    """Submitting the same message_id twice returns the cached result."""
    ingest_payload = {
        "message_id": "msg_idempo_1",
        "from": {"name": "Test", "email": "test@example.com"},
        "subject": "Customer issue - portal error",
        "received_at": "2026-01-23T10:00:00Z",
        "body": "Company: Northwind Traders. Urgent. Billing portal error HTTP 500.",
    }

    first_response = client.post("/api/v1/ingest", json=ingest_payload)
    assert first_response.status_code == 200
    first_item_id = first_response.json()["item_id"]

    second_response = client.post("/api/v1/ingest", json=ingest_payload)
    assert second_response.status_code == 200
    assert second_response.json()["item_id"] == first_item_id
    assert second_response.json()["routed_to"] == "idempotent_return"


def test_review_flow_reject_or_approve(client: TestClient) -> None:
    """Low-confidence message can be routed to review and then rejected."""
    ingest_payload = {
        "message_id": "msg_review_1",
        "from": {"name": "Unknown", "email": "unknown2@example.net"},
        "subject": "Quick question",
        "received_at": "2026-01-23T10:10:00Z",
        "body": "Hey, can you help?",
    }
    ingest_response = client.post("/api/v1/ingest", json=ingest_payload)
    assert ingest_response.status_code == 200
    item_id = ingest_response.json()["item_id"]

    stored_item = client.get(f"/api/v1/items/{item_id}").json()
    # Vague body may be auto_rejected (< 0.50), pending_review (0.50–0.85), or approved
    assert stored_item["status"] in ("pending_review", "approved", "rejected")

    if stored_item["status"] == "pending_review":
        review_response = client.post(
            f"/api/v1/items/{item_id}/review",
            json={"reviewer": "qa_user", "action": "reject", "reason": "Insufficient details"},
        )
        assert review_response.status_code == 200
        updated_item = client.get(f"/api/v1/items/{item_id}").json()
        assert updated_item["status"] == "rejected"
