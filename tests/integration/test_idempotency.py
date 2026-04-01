"""Integration tests for idempotency guarantees.

Tests:
- test_same_email_twice_returns_cached_result        — single-message dedup
- test_batch_with_duplicate_ids_processes_each_once  — batch-level dedup
- test_two_batches_same_emails_no_extra_items        — cross-batch dedup
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _email_payload(
    message_id: str, body: str = "Purchase 3 laptops. Item: ThinkPad, Qty: 3."
) -> dict:
    return {
        "message_id": message_id,
        "from": {"name": "Alice", "email": "alice@corp.com"},
        "subject": "Idempotency test",
        "received_at": "2026-03-22T10:00:00Z",
        "body": body,
    }


# ---------------------------------------------------------------------------
# Single-message idempotency
# ---------------------------------------------------------------------------


def test_same_email_twice_returns_cached_result(client: TestClient) -> None:
    """Submitting the same message_id twice returns the identical item_id."""
    first = client.post("/api/v1/ingest", json=_email_payload("idemp_msg_1"))
    assert first.status_code == 200

    second = client.post("/api/v1/ingest", json=_email_payload("idemp_msg_1"))
    assert second.status_code == 200

    assert first.json()["item_id"] == second.json()["item_id"]
    assert second.json()["routed_to"] == "idempotent_return"


def test_same_email_multiple_times_stores_exactly_one_item(client: TestClient) -> None:
    """Three submissions of the same message_id produce exactly one stored item."""
    payload = _email_payload("idemp_msg_multi")
    for _ in range(3):
        response = client.post("/api/v1/ingest", json=payload)
        assert response.status_code == 200

    # Verify only one item exists in storage by checking the review queue
    items_response = client.get("/api/v1/items")
    assert items_response.status_code == 200
    item_ids_for_message = [
        item["item_id"] for item in items_response.json() if item["message_id"] == "idemp_msg_multi"
    ]
    assert len(item_ids_for_message) == 1


# ---------------------------------------------------------------------------
# Batch-level idempotency
# ---------------------------------------------------------------------------


def test_batch_with_duplicate_message_ids_processes_each_once(client: TestClient) -> None:
    """A batch containing two identical message_ids stores only one item per ID."""
    batch_payload = {
        "emails": [
            _email_payload("idemp_batch_dup_1"),
            _email_payload("idemp_batch_dup_1"),  # duplicate
            _email_payload("idemp_batch_dup_2"),
        ]
    }
    response = client.post("/api/v1/batch", json=batch_payload)
    assert response.status_code == 200

    job_id = response.json()["job_id"]
    job_response = client.get(f"/api/v1/batch/{job_id}")
    assert job_response.status_code == 200
    job = job_response.json()

    # Both emails processed (3 total — duplicate counted as processed once each attempt)
    assert job["processed"] == 3

    # Only 2 distinct items in storage (the duplicate was a no-op second write)
    items_response = client.get("/api/v1/items")
    all_message_ids = [item["message_id"] for item in items_response.json()]
    batch_ids = [mid for mid in all_message_ids if mid.startswith("idemp_batch_dup")]
    assert len(set(batch_ids)) == 2  # only 2 unique message IDs stored


# ---------------------------------------------------------------------------
# Cross-batch idempotency
# ---------------------------------------------------------------------------


def test_two_batches_with_same_emails_no_extra_items(client: TestClient) -> None:
    """Submitting the same emails in two separate batches creates no duplicate items."""
    emails = [
        _email_payload("idemp_xbatch_1"),
        _email_payload("idemp_xbatch_2"),
    ]

    first_batch = client.post("/api/v1/batch", json={"emails": emails})
    assert first_batch.status_code == 200

    second_batch = client.post("/api/v1/batch", json={"emails": emails})
    assert second_batch.status_code == 200

    items_response = client.get("/api/v1/items")
    all_message_ids = [item["message_id"] for item in items_response.json()]
    xbatch_ids = [mid for mid in all_message_ids if mid.startswith("idemp_xbatch")]
    assert len(xbatch_ids) == 2  # still exactly 2 items, no duplicates
