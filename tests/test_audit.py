"""Tests for audit logging through the workflow pipeline.

Verifies that audit entries contain the required fields and that
the full pipeline (ingest → extract → route → audit) is traceable.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


PURCHASE_PAYLOAD = {
    "message_id": "audit_msg_001",
    "from": {"name": "Alice", "email": "alice@example.com"},
    "subject": "Purchase request — ThinkPad",
    "received_at": "2026-03-01T09:00:00Z",
    "body": "Please purchase 2x ThinkPad T14s. Item: ThinkPad T14s, Qty: 2. Company: Acme Corp.",
}

VAGUE_PAYLOAD = {
    "message_id": "audit_msg_002",
    "from": {"name": "Bob", "email": "bob@example.com"},
    "subject": "Question",
    "received_at": "2026-03-01T09:05:00Z",
    "body": "Hey",
}


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


def test_audit_trail_created_on_ingest(client):
    client.post("/api/v1/ingest", json=PURCHASE_PAYLOAD)
    item_id = client.post("/api/v1/ingest", json={**PURCHASE_PAYLOAD, "message_id": "audit_trail_1"}).json()["item_id"]
    audit = client.get(f"/api/v1/items/{item_id}/audit").json()
    assert len(audit) >= 1


def test_audit_first_event_is_ingested(client):
    r = client.post("/api/v1/ingest", json={**PURCHASE_PAYLOAD, "message_id": "audit_first_1"})
    item_id = r.json()["item_id"]
    audit = client.get(f"/api/v1/items/{item_id}/audit").json()
    assert audit[0]["event_type"] == "ingested"


def test_audit_ingested_details_contain_confidence(client):
    r = client.post("/api/v1/ingest", json={**PURCHASE_PAYLOAD, "message_id": "audit_conf_1"})
    item_id = r.json()["item_id"]
    audit = client.get(f"/api/v1/items/{item_id}/audit").json()
    ingested = next(e for e in audit if e["event_type"] == "ingested")
    assert "confidence" in ingested["details"]
    assert isinstance(ingested["details"]["confidence"], float)


def test_audit_contains_routing_action(client):
    r = client.post("/api/v1/ingest", json={**PURCHASE_PAYLOAD, "message_id": "audit_route_1"})
    item_id = r.json()["item_id"]
    audit = client.get(f"/api/v1/items/{item_id}/audit").json()
    ingested = next(e for e in audit if e["event_type"] == "ingested")
    assert "routing_action" in ingested["details"]
    assert ingested["details"]["routing_action"] in ("auto_approve", "human_review", "auto_reject")


def test_audit_contains_input_hash(client):
    r = client.post("/api/v1/ingest", json={**PURCHASE_PAYLOAD, "message_id": "audit_hash_1"})
    item_id = r.json()["item_id"]
    audit = client.get(f"/api/v1/items/{item_id}/audit").json()
    ingested = next(e for e in audit if e["event_type"] == "ingested")
    assert "input_hash" in ingested["details"]
    assert len(ingested["details"]["input_hash"]) == 16  # 16-char hex digest


def test_audit_contains_prompt_version(client):
    r = client.post("/api/v1/ingest", json={**PURCHASE_PAYLOAD, "message_id": "audit_prompt_1"})
    item_id = r.json()["item_id"]
    audit = client.get(f"/api/v1/items/{item_id}/audit").json()
    ingested = next(e for e in audit if e["event_type"] == "ingested")
    assert ingested["details"]["prompt_version"] == "email_extraction_v1"


def test_human_review_adds_audit_entry(client):
    r = client.post("/api/v1/ingest", json={**VAGUE_PAYLOAD, "message_id": "audit_review_1"})
    item_id = r.json()["item_id"]
    item = client.get(f"/api/v1/items/{item_id}").json()

    if item["status"] == "pending_review":
        client.post(
            f"/api/v1/items/{item_id}/review",
            json={"reviewer": "qa_user", "action": "reject", "reason": "Too vague"},
        )
        audit = client.get(f"/api/v1/items/{item_id}/audit").json()
        event_types = [e["event_type"] for e in audit]
        assert "rejected" in event_types
