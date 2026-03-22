"""Integration tests for the human review queue and audit trail.

Tests:
- GET /api/v1/review returns items with status=pending_review
- POST /api/v1/review/{id} approve records an audit event with event_type=approved
- POST /api/v1/review/{id} reject records an audit event with event_type=rejected

All external services (AI, Slack, CRM) use mock mode set by the autouse
_isolate_test_db fixture in conftest.py.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BILLING_ERROR_PAYLOAD = {
    "message_id": "msg_billing_error_1",
    "from": {"name": "Jane Smith", "email": "jane@northwind.com"},
    "subject": "Billing portal error — cannot access invoices",
    "received_at": "2026-03-22T09:00:00Z",
    "body": (
        "We are getting a billing error on the portal since this morning. "
        "Customers cannot access their invoices. HTTP 500 on every page load. "
        "Company: Northwind Traders. Please investigate urgently."
    ),
}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Yield a TestClient that triggers the FastAPI lifespan on entry."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def pending_item_id(client: TestClient) -> str:
    """Ingest a billing-error message and return its item_id.

    The mock AI client routes this body to _MOCK_ISSUE (customer_issue,
    company present, 1 extraction note, no due_date) → confidence ≈ 0.83
    → human_review band → status=pending_review.
    """
    ingest_response = client.post("/api/v1/ingest", json=_BILLING_ERROR_PAYLOAD)
    assert ingest_response.status_code == 200, ingest_response.text
    data = ingest_response.json()
    assert data["status"] == "pending_review", (
        f"Expected pending_review but got {data['status']} (confidence={data['confidence']})"
    )
    return data["item_id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_review_queue_returns_pending_items(client: TestClient, pending_item_id: str) -> None:
    """GET /review returns the pending item with correct fields."""
    review_response = client.get("/api/v1/review")
    assert review_response.status_code == 200

    payload = review_response.json()
    assert "items" in payload
    assert "total" in payload
    assert payload["total"] >= 1

    item_ids = [item["item_id"] for item in payload["items"]]
    assert pending_item_id in item_ids

    pending_item = next(i for i in payload["items"] if i["item_id"] == pending_item_id)
    assert pending_item["status"] == "pending_review"
    assert 0.0 <= pending_item["confidence"] <= 1.0


def test_approve_review_logs_to_audit(client: TestClient, pending_item_id: str) -> None:
    """POST /review/{id} approve updates status and writes an approved audit event."""
    approve_response = client.post(
        f"/api/v1/review/{pending_item_id}",
        json={"reviewer": "alice", "action": "approve", "reason": "Looks good"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    # Item status must be updated
    item_response = client.get(f"/api/v1/items/{pending_item_id}")
    assert item_response.status_code == 200
    assert item_response.json()["status"] == "approved"

    # Audit trail must contain an approved event
    audit_response = client.get(f"/api/v1/items/{pending_item_id}/audit")
    assert audit_response.status_code == 200
    audit_events = audit_response.json()
    event_types = [e["event_type"] for e in audit_events]
    assert "approved" in event_types, f"No approved event found — events: {event_types}"

    approved_event = next(e for e in audit_events if e["event_type"] == "approved")
    assert approved_event["actor"] == "alice"


def test_reject_review_logs_to_audit(client: TestClient, pending_item_id: str) -> None:
    """POST /review/{id} reject updates status and writes a rejected audit event."""
    reject_response = client.post(
        f"/api/v1/review/{pending_item_id}",
        json={"reviewer": "bob", "action": "reject", "reason": "Insufficient detail"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    # Item status must be updated
    item_response = client.get(f"/api/v1/items/{pending_item_id}")
    assert item_response.status_code == 200
    assert item_response.json()["status"] == "rejected"

    # Audit trail must contain a rejected event
    audit_response = client.get(f"/api/v1/items/{pending_item_id}/audit")
    assert audit_response.status_code == 200
    audit_events = audit_response.json()
    event_types = [e["event_type"] for e in audit_events]
    assert "rejected" in event_types, f"No rejected event found — events: {event_types}"

    rejected_event = next(e for e in audit_events if e["event_type"] == "rejected")
    assert rejected_event["actor"] == "bob"
    assert rejected_event["details"]["reason"] == "Insufficient detail"
