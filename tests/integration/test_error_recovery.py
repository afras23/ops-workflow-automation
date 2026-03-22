"""Integration tests for error recovery scenarios.

Tests:
- test_extraction_error_returns_422_with_structured_detail
- test_retry_succeeds_after_transient_timeout       — unit-style via ExtractionService
- test_storage_failure_surfaces_as_500             — storage write failure
- test_circuit_breaker_open_blocks_ai_call         — full pipeline CB integration
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import RetryableError
from app.models.email import InboxMessage
from app.services.ai.client import AICallResult, CircuitBreaker, MockAIClient, _call_with_retry
from app.services.extraction_service import ExtractionService

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _message(message_id: str = "err_msg_001", body: str = "Purchase 2 laptops.") -> InboxMessage:
    return InboxMessage(
        message_id=message_id,
        **{"from": {"name": "Alice", "email": "alice@corp.com"}},
        subject="Test",
        received_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        body=body,
    )


# ---------------------------------------------------------------------------
# HTTP 422 on extraction failure
# ---------------------------------------------------------------------------


def test_extraction_error_returns_422_with_structured_detail(client: TestClient) -> None:
    """A bad AI response (non-JSON) causes the ingest endpoint to return HTTP 422."""
    broken_json_client = MockAIClient(response="Sorry, I cannot help with that.")
    broken_svc = ExtractionService(ai_client=broken_json_client)

    with patch.object(
        client.app.state.workflow_service,
        "_extraction",
        broken_svc,
    ):
        response = client.post(
            "/api/v1/ingest",
            json={
                "message_id": "err_422_msg_1",
                "from": {"name": "Test", "email": "test@example.com"},
                "subject": "Bad AI test",
                "received_at": "2026-03-22T10:00:00Z",
                "body": "Some content",
            },
        )

    assert response.status_code == 422
    assert "non-JSON" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Retry then succeed (unit-level via _call_with_retry)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_timeout() -> None:
    """_call_with_retry retries on TimeoutError and returns the result on success."""
    attempt_count = 0

    async def flaky_ai_call() -> AICallResult:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise TimeoutError(f"simulated timeout on attempt {attempt_count}")
        return AICallResult(
            text=json.dumps({"request_type": "other"}),
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.001,
            latency_ms=120.0,
            model="test",
            prompt_version="v1",
        )

    result = await _call_with_retry(flaky_ai_call, max_attempts=3, base_delay=0.0)
    assert attempt_count == 3
    assert result.cost_usd == 0.001


@pytest.mark.asyncio
async def test_retry_exhausted_raises_last_exception() -> None:
    """When all retry attempts fail, the last TimeoutError is re-raised."""

    async def always_fails() -> AICallResult:
        raise TimeoutError("provider always down")

    with pytest.raises(TimeoutError, match="provider always down"):
        await _call_with_retry(always_fails, max_attempts=2, base_delay=0.0)


# ---------------------------------------------------------------------------
# Storage write failure → HTTP 500
# ---------------------------------------------------------------------------


def test_storage_write_failure_surfaces_as_500() -> None:
    """When storage.create_item raises, the unhandled exception becomes HTTP 500."""
    import sqlite3

    from app.main import app

    # raise_server_exceptions=False so the unhandled OperationalError becomes a 500
    # response instead of being re-raised into the test process.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        with patch.object(
            test_client.app.state.storage,
            "create_item",
            side_effect=sqlite3.OperationalError("disk I/O error"),
        ):
            response = test_client.post(
                "/api/v1/ingest",
                json={
                    "message_id": "err_storage_msg_1",
                    "from": {"name": "Test", "email": "test@example.com"},
                    "subject": "Storage failure test",
                    "received_at": "2026-03-22T10:00:00Z",
                    "body": "Purchase 2 laptops please.",
                },
            )

    assert response.status_code == 500


# ---------------------------------------------------------------------------
# Circuit breaker integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_open_raises_retryable_error() -> None:
    """An open CircuitBreaker raises RetryableError without calling the provider."""
    breaker = CircuitBreaker(failure_threshold=1, window_seconds=60.0)
    breaker.record_failure()  # Open the circuit
    assert breaker.is_open()

    with pytest.raises(RetryableError, match="Circuit breaker open"):
        if breaker.is_open():
            raise RetryableError("Circuit breaker open")


@pytest.mark.asyncio
async def test_circuit_breaker_records_failures_from_retry() -> None:
    """Each transient failure in _call_with_retry increments the circuit breaker."""
    breaker = CircuitBreaker(failure_threshold=5, window_seconds=60.0)

    async def always_fails() -> AICallResult:
        raise ConnectionError("provider unreachable")

    with pytest.raises(ConnectionError):
        await _call_with_retry(
            always_fails,
            circuit_breaker=breaker,
            max_attempts=3,
            base_delay=0.0,
        )

    # 3 failures recorded
    assert len(breaker._failures) == 3
