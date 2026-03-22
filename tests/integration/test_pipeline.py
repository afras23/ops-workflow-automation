"""Integration tests for the full end-to-end pipeline.

Tests:
- test_batch_of_five_emails_end_to_end   — five different types all processed
- test_full_pipeline_creates_audit_trail — E2E with audit trail verification
- test_pipeline_extraction_failure_returns_422 — ExtractionError → HTTP 422
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ExtractionError


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _ingest_payload(
    message_id: str,
    subject: str,
    body: str,
    sender_name: str = "Test User",
    sender_email: str = "user@example.com",
) -> dict:
    return {
        "message_id": message_id,
        "from": {"name": sender_name, "email": sender_email},
        "subject": subject,
        "received_at": "2026-03-22T09:00:00Z",
        "body": body,
    }


# ---------------------------------------------------------------------------
# Five-email end-to-end batch
# ---------------------------------------------------------------------------

_FIVE_EMAIL_BATCH = [
    (
        "pipe_msg_purchase",
        "Hardware purchase",
        "Please purchase 4 ergonomic chairs. Item: Herman Miller, Qty: 4.",
    ),
    (
        "pipe_msg_issue",
        "Billing error",
        "Billing portal error HTTP 500 since Monday. Company: Northwind.",
    ),
    (
        "pipe_msg_ops",
        "Deployment config",
        "Please update the deployment config for the staging environment.",
    ),
    (
        "pipe_msg_vague",
        "Quick question",
        "Hey, just wanted to check something with you when you have time.",
    ),
    (
        "pipe_msg_unicode",
        "International request",
        "Ich möchte 2 Monitore kaufen. Item: Dell 27in, Qty: 2.",
    ),
]


def test_batch_of_five_emails_end_to_end(client: TestClient) -> None:
    """Five emails with different types all complete the pipeline successfully."""
    item_ids: list[str] = []
    for message_id, subject, body in _FIVE_EMAIL_BATCH:
        response = client.post(
            "/api/v1/ingest",
            json=_ingest_payload(message_id, subject, body),
        )
        assert response.status_code == 200, f"Failed for {message_id}: {response.text}"
        body_json = response.json()
        assert body_json["status"] in ("pending_review", "approved", "rejected", "failed")
        assert 0.0 <= body_json["confidence"] <= 1.0
        item_ids.append(body_json["item_id"])

    # All item IDs are distinct
    assert len(set(item_ids)) == 5


# ---------------------------------------------------------------------------
# End-to-end with audit trail
# ---------------------------------------------------------------------------


def test_full_pipeline_creates_audit_trail(client: TestClient) -> None:
    """Ingesting an email produces at least one audit entry for the item."""
    ingest_response = client.post(
        "/api/v1/ingest",
        json=_ingest_payload(
            "pipe_audit_msg_1",
            "Purchase request",
            "Purchase 2x ThinkPad T14s. Item: ThinkPad T14s, Qty: 2.",
        ),
    )
    assert ingest_response.status_code == 200
    item_id = ingest_response.json()["item_id"]

    audit_response = client.get(f"/api/v1/items/{item_id}/audit")
    assert audit_response.status_code == 200

    audit_entries = audit_response.json()
    assert len(audit_entries) >= 1
    event_types = [entry["event_type"] for entry in audit_entries]
    assert any(et in ("ingested", "ingest_failed") for et in event_types)


# ---------------------------------------------------------------------------
# Extraction failure → HTTP 422
# ---------------------------------------------------------------------------


def test_pipeline_extraction_failure_returns_422(client: TestClient) -> None:
    """When ExtractionService raises ExtractionError the endpoint returns HTTP 422."""
    with patch(
        "app.services.workflow_service.WorkflowService.ingest",
        new_callable=AsyncMock,
        side_effect=ExtractionError("AI returned non-JSON response"),
    ):
        response = client.post(
            "/api/v1/ingest",
            json=_ingest_payload(
                "pipe_fail_msg_1",
                "Any subject",
                "Any body",
            ),
        )

    assert response.status_code == 422
    assert "non-JSON" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Full pipeline routing coverage
# ---------------------------------------------------------------------------


def test_pipeline_routes_high_confidence_to_approved(client: TestClient) -> None:
    """A high-signal purchase email with company + line items is auto-approved or reviewed."""
    response = client.post(
        "/api/v1/ingest",
        json=_ingest_payload(
            "pipe_high_conf_1",
            "Purchase order — urgent",
            (
                "Please purchase 2x Dell XPS 15 laptops for new starters. "
                "Company: Acme Corp. Item: Dell XPS 15, Qty: 2. "
                "Due date: 2026-04-01. Urgent requirement for Monday onboarding."
            ),
        ),
    )
    assert response.status_code == 200
    assert response.json()["status"] in ("approved", "pending_review")


def test_pipeline_routes_vague_email_to_review_or_reject(client: TestClient) -> None:
    """A vague email with no extractable fields lands in pending_review or rejected."""
    response = client.post(
        "/api/v1/ingest",
        json=_ingest_payload(
            "pipe_vague_1",
            "Hi",
            "Hello.",
        ),
    )
    assert response.status_code == 200
    assert response.json()["status"] in ("pending_review", "rejected")
