import os
import json
import pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def client():
    # Import here so env vars from conftest are applied before app initializes
    from app.main import app
    return TestClient(app)

def test_ingest_idempotent(client):
    payload = {
        "message_id": "msg_idempo_1",
        "from": {"name": "Test", "email": "test@example.com"},
        "subject": "Customer issue - portal error",
        "received_at": "2026-01-23T10:00:00Z",
        "body": "Company: Northwind Traders. Urgent. Billing portal error HTTP 500."
    }

    r1 = client.post("/ingest", json=payload)
    assert r1.status_code == 200
    item_id_1 = r1.json()["item_id"]

    r2 = client.post("/ingest", json=payload)
    assert r2.status_code == 200
    assert r2.json()["item_id"] == item_id_1
    assert r2.json()["routed_to"] == "idempotent_return"

def test_review_flow_reject_or_approve(client):
    # Likely low confidence -> pending_review
    payload = {
        "message_id": "msg_review_1",
        "from": {"name": "Unknown", "email": "unknown2@example.net"},
        "subject": "Quick question",
        "received_at": "2026-01-23T10:10:00Z",
        "body": "Hey, can you help?"
    }
    r = client.post("/ingest", json=payload)
    assert r.status_code == 200
    item_id = r.json()["item_id"]

    # Should be pending_review
    item = client.get(f"/items/{item_id}").json()
    assert item["status"] in ("pending_review", "approved")  # depending on threshold

    if item["status"] == "pending_review":
        rr = client.post(f"/items/{item_id}/review", json={"reviewer": "qa_user", "action": "reject", "reason": "Insufficient details"})
        assert rr.status_code == 200
        item2 = client.get(f"/items/{item_id}").json()
        assert item2["status"] == "rejected"
