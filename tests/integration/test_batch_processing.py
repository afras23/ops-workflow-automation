"""Integration tests for batch ingest processing.

Tests:
- test_batch_processing_creates_job           — POST /batch returns a job with a job_id
- test_batch_progress_tracks_correctly        — counters reflect every email processed
- test_failed_email_doesnt_abort_batch        — ExtractionError is isolated; batch completes
- test_duplicate_email_skipped                — same message_id processed twice without error
- test_concurrent_batch_no_corruption         — 10 emails via asyncio.gather → correct counts

The _isolate_test_db autouse fixture from conftest.py redirects storage to a
per-test tmp_path directory and sets AI_PROVIDER=mock so no real calls are made.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ExtractionError

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Yield a TestClient that triggers the FastAPI lifespan."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _make_email(n: int, *, subject: str = "Billing portal error") -> dict:
    """Build a minimal inbox message payload with a unique message_id.

    Args:
        n: Sequence number used to ensure message_id uniqueness.
        subject: Subject line (controls MockAIClient keyword routing).

    Returns:
        Dict suitable for use in a BatchIngestRequest.emails list.
    """
    return {
        "message_id": f"msg_batch_{n}",
        "from": {"name": "Test User", "email": f"user{n}@example.com"},
        "subject": subject,
        "received_at": "2026-03-22T10:00:00Z",
        "body": (
            f"Billing error on the portal (email #{n}). "
            "Company: Northwind Traders. HTTP 500 since this morning."
        ),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_batch_processing_creates_job(client: TestClient) -> None:
    """POST /batch returns a batch job with a non-empty job_id and status=complete."""
    response = client.post("/api/v1/batch", json={"emails": [_make_email(1), _make_email(2)]})
    assert response.status_code == 200, response.text

    job = response.json()
    assert job["job_id"], "job_id must be non-empty"
    assert job["status"] == "complete"
    assert job["total"] == 2


def test_batch_progress_tracks_correctly(client: TestClient) -> None:
    """processed + succeeded counters reflect every email in the batch."""
    emails = [_make_email(i) for i in range(1, 4)]  # 3 emails
    response = client.post("/api/v1/batch", json={"emails": emails})
    assert response.status_code == 200, response.text

    job = response.json()
    assert job["total"] == 3
    assert job["processed"] == 3
    assert job["succeeded"] == 3
    assert job["failed_count"] == 0

    # GET /batch/{job_id} must return the same completed job
    get_response = client.get(f"/api/v1/batch/{job['job_id']}")
    assert get_response.status_code == 200
    retrieved = get_response.json()
    assert retrieved["job_id"] == job["job_id"]
    assert retrieved["status"] == "complete"
    assert retrieved["processed"] == 3


def test_failed_email_doesnt_abort_batch(client: TestClient) -> None:
    """ExtractionError on one email increments failed_count; batch still completes."""
    # Patch WorkflowService.ingest so the second call always raises ExtractionError.
    original_ingest = client.app.state.workflow_service.ingest
    call_count = 0

    async def patched_ingest(message):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ExtractionError(
                "Injected test failure", context={"message_id": message.message_id}
            )
        return await original_ingest(message)

    client.app.state.workflow_service.ingest = patched_ingest

    try:
        emails = [_make_email(i) for i in range(1, 4)]  # 3 emails, 2nd will fail
        response = client.post("/api/v1/batch", json={"emails": emails})
        assert response.status_code == 200, response.text

        job = response.json()
        assert job["status"] == "complete", "Batch must complete despite one failure"
        assert job["total"] == 3
        assert job["processed"] == 3
        assert job["failed_count"] == 1
        assert job["succeeded"] == 2
    finally:
        client.app.state.workflow_service.ingest = original_ingest


def test_duplicate_email_skipped(client: TestClient) -> None:
    """Submitting the same message_id twice in one batch causes no errors."""
    duplicate = _make_email(1)
    response = client.post("/api/v1/batch", json={"emails": [duplicate, duplicate]})
    assert response.status_code == 200, response.text

    job = response.json()
    assert job["status"] == "complete"
    assert job["total"] == 2
    assert job["processed"] == 2
    # Both succeed: second hit idempotent_return (not an error)
    assert job["failed_count"] == 0


def test_concurrent_batch_no_corruption(client: TestClient) -> None:
    """10 emails processed concurrently via asyncio.gather produce correct final counts.

    BatchService uses asyncio.gather internally and Storage uses atomic SQL
    increments. This test verifies that concurrent progress updates do not
    corrupt the counters.
    """
    emails = [_make_email(i) for i in range(1, 11)]  # 10 unique emails
    response = client.post("/api/v1/batch", json={"emails": emails})
    assert response.status_code == 200, response.text

    job = response.json()
    assert job["status"] == "complete"
    assert job["total"] == 10
    assert job["processed"] == 10, f"processed={job['processed']} expected 10"
    assert job["succeeded"] == 10, f"succeeded={job['succeeded']} expected 10"
    assert job["failed_count"] == 0
    # Invariant: processed == succeeded + failed_count
    assert job["processed"] == job["succeeded"] + job["failed_count"]
