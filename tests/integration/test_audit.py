"""Integration tests for audit logging through the workflow pipeline.

Verifies that audit entries contain the required fields and that
the full pipeline (ingest → extract → route → audit) is traceable.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

_PURCHASE_PAYLOAD = {
    "message_id": "audit_msg_001",
    "from": {"name": "Alice", "email": "alice@example.com"},
    "subject": "Purchase request — ThinkPad",
    "received_at": "2026-03-01T09:00:00Z",
    "body": "Please purchase 2x ThinkPad T14s. Item: ThinkPad T14s, Qty: 2. Company: Acme Corp.",
}

_VAGUE_PAYLOAD = {
    "message_id": "audit_msg_002",
    "from": {"name": "Bob", "email": "bob@example.com"},
    "subject": "Question",
    "received_at": "2026-03-01T09:05:00Z",
    "body": "Hey",
}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Yield a TestClient that triggers the FastAPI lifespan on entry."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_audit_trail_created_on_ingest(client: TestClient) -> None:
    ingest_response = client.post(
        "/api/v1/ingest", json={**_PURCHASE_PAYLOAD, "message_id": "audit_trail_1"}
    )
    item_id = ingest_response.json()["item_id"]
    audit_log = client.get(f"/api/v1/items/{item_id}/audit").json()
    assert len(audit_log) >= 1


def test_audit_first_event_is_ingested(client: TestClient) -> None:
    ingest_response = client.post(
        "/api/v1/ingest", json={**_PURCHASE_PAYLOAD, "message_id": "audit_first_1"}
    )
    item_id = ingest_response.json()["item_id"]
    audit_log = client.get(f"/api/v1/items/{item_id}/audit").json()
    assert audit_log[0]["event_type"] == "ingested"


def test_audit_ingested_details_contain_confidence(client: TestClient) -> None:
    ingest_response = client.post(
        "/api/v1/ingest", json={**_PURCHASE_PAYLOAD, "message_id": "audit_conf_1"}
    )
    item_id = ingest_response.json()["item_id"]
    audit_log = client.get(f"/api/v1/items/{item_id}/audit").json()
    ingested_event = next(e for e in audit_log if e["event_type"] == "ingested")
    assert "confidence" in ingested_event["details"]
    assert isinstance(ingested_event["details"]["confidence"], float)


def test_audit_contains_routing_action(client: TestClient) -> None:
    ingest_response = client.post(
        "/api/v1/ingest", json={**_PURCHASE_PAYLOAD, "message_id": "audit_route_1"}
    )
    item_id = ingest_response.json()["item_id"]
    audit_log = client.get(f"/api/v1/items/{item_id}/audit").json()
    ingested_event = next(e for e in audit_log if e["event_type"] == "ingested")
    assert "routing_action" in ingested_event["details"]
    assert ingested_event["details"]["routing_action"] in (
        "auto_approve",
        "human_review",
        "auto_reject",
    )


def test_audit_contains_input_hash(client: TestClient) -> None:
    ingest_response = client.post(
        "/api/v1/ingest", json={**_PURCHASE_PAYLOAD, "message_id": "audit_hash_1"}
    )
    item_id = ingest_response.json()["item_id"]
    audit_log = client.get(f"/api/v1/items/{item_id}/audit").json()
    ingested_event = next(e for e in audit_log if e["event_type"] == "ingested")
    assert "input_hash" in ingested_event["details"]
    assert len(ingested_event["details"]["input_hash"]) == 16


def test_audit_contains_prompt_version(client: TestClient) -> None:
    ingest_response = client.post(
        "/api/v1/ingest", json={**_PURCHASE_PAYLOAD, "message_id": "audit_prompt_1"}
    )
    item_id = ingest_response.json()["item_id"]
    audit_log = client.get(f"/api/v1/items/{item_id}/audit").json()
    ingested_event = next(e for e in audit_log if e["event_type"] == "ingested")
    assert ingested_event["details"]["prompt_version"] == "email_extraction_v1"


def test_human_review_adds_audit_entry(client: TestClient) -> None:
    ingest_response = client.post(
        "/api/v1/ingest", json={**_VAGUE_PAYLOAD, "message_id": "audit_review_1"}
    )
    item_id = ingest_response.json()["item_id"]
    stored_item = client.get(f"/api/v1/items/{item_id}").json()

    if stored_item["status"] == "pending_review":
        client.post(
            f"/api/v1/items/{item_id}/review",
            json={"reviewer": "qa_user", "action": "reject", "reason": "Too vague"},
        )
        audit_log = client.get(f"/api/v1/items/{item_id}/audit").json()
        event_types = [e["event_type"] for e in audit_log]
        assert "rejected" in event_types
