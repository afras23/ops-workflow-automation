"""Unit tests for AI client: cost tracking, circuit breaker, retry, and mock client.

All tests are pure unit tests — no real API calls, no I/O.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import CostLimitExceeded
from app.services.ai.client import (
    AICallResult,
    CircuitBreaker,
    DailyCostTracker,
    MockAIClient,
    _call_with_retry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(cost_usd: float = 0.01) -> AICallResult:
    return AICallResult(
        text="{}",
        tokens_in=100,
        tokens_out=50,
        cost_usd=cost_usd,
        latency_ms=42.0,
        model="test",
        prompt_version="v1",
    )


# ---------------------------------------------------------------------------
# DailyCostTracker
# ---------------------------------------------------------------------------


def test_cost_tracking_accumulates_correctly() -> None:
    """Multiple add() calls accumulate into total_today()."""
    tracker = DailyCostTracker()
    tracker.add(0.01)
    tracker.add(0.02)
    tracker.add(0.003)
    assert abs(tracker.total_today() - 0.033) < 1e-10


def test_cost_limit_prevents_calls() -> None:
    """check_limit() raises CostLimitExceeded once the daily total reaches the cap."""
    tracker = DailyCostTracker()
    tracker.add(10.0)
    with pytest.raises(CostLimitExceeded, match="Daily cost limit"):
        tracker.check_limit(10.0)


def test_cost_limit_not_raised_below_cap() -> None:
    tracker = DailyCostTracker()
    tracker.add(9.99)
    tracker.check_limit(10.0)  # should not raise


def test_cost_tracker_resets_when_date_changes() -> None:
    """total_today() returns 0.0 when the internal date is stale."""
    from datetime import date

    tracker = DailyCostTracker()
    tracker.add(5.0)
    assert tracker.total_today() == 5.0

    tracker._date = date(2000, 1, 1)  # simulate a new day
    assert tracker.total_today() == 0.0


def test_cost_tracker_add_resets_on_stale_date() -> None:
    from datetime import date

    tracker = DailyCostTracker()
    tracker.add(5.0)
    tracker._date = date(2000, 1, 1)

    tracker.add(1.0)
    assert abs(tracker.total_today() - 1.0) < 1e-10


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_opens_after_failures() -> None:
    """Circuit opens exactly when failure count reaches the threshold."""
    cb = CircuitBreaker(failure_threshold=5, window_seconds=60.0)
    assert not cb.is_open()
    for _ in range(5):
        cb.record_failure()
    assert cb.is_open()


def test_circuit_breaker_stays_closed_below_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=5, window_seconds=60.0)
    for _ in range(4):
        cb.record_failure()
    assert not cb.is_open()


def test_circuit_breaker_closes_after_success() -> None:
    cb = CircuitBreaker(failure_threshold=3, window_seconds=60.0)
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open()
    cb.record_success()
    assert not cb.is_open()


def test_circuit_breaker_prunes_stale_failures() -> None:
    """Failures older than window_seconds are evicted and don't count."""
    import time

    cb = CircuitBreaker(failure_threshold=3, window_seconds=0.05)
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open()

    time.sleep(0.1)
    assert not cb.is_open()


# ---------------------------------------------------------------------------
# _call_with_retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_timeout() -> None:
    """Succeeds on the third attempt after two TimeoutErrors."""
    attempts = 0

    async def flaky_call() -> AICallResult:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("provider timeout")
        return _make_result()

    result = await _call_with_retry(flaky_call, max_attempts=3, base_delay=0.0)
    assert result.text == "{}"
    assert attempts == 3


@pytest.mark.asyncio
async def test_retry_raises_after_max_attempts() -> None:
    """Re-raises the last exception when all attempts fail."""

    async def always_fail() -> AICallResult:
        raise TimeoutError("always fails")

    with pytest.raises(TimeoutError, match="always fails"):
        await _call_with_retry(always_fail, max_attempts=3, base_delay=0.0)


@pytest.mark.asyncio
async def test_retry_calls_circuit_breaker_on_each_failure() -> None:
    """Each transient failure increments the circuit breaker, not just the final one."""
    cb = CircuitBreaker(failure_threshold=10, window_seconds=60.0)
    call_count = 0

    async def fail_twice() -> AICallResult:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("transient")
        return _make_result()

    await _call_with_retry(fail_twice, circuit_breaker=cb, max_attempts=3, base_delay=0.0)
    assert len(cb._failures) == 2


@pytest.mark.asyncio
async def test_no_retry_on_first_success() -> None:
    calls = 0

    async def succeed() -> AICallResult:
        nonlocal calls
        calls += 1
        return _make_result()

    await _call_with_retry(succeed, base_delay=0.0)
    assert calls == 1


# ---------------------------------------------------------------------------
# MockAIClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_client_returns_ai_call_result() -> None:
    client = MockAIClient()
    result = await client.complete(system="", user="purchase request", prompt_version="v1")
    assert isinstance(result, AICallResult)
    assert result.model == "mock"
    assert result.cost_usd == 0.0
    assert result.tokens_in == 0
    assert result.tokens_out == 0


@pytest.mark.asyncio
async def test_mock_client_fixed_response_returned_as_text() -> None:
    client = MockAIClient(response='{"test": true}')
    result = await client.complete(system="", user="anything")
    assert result.text == '{"test": true}'


@pytest.mark.asyncio
async def test_mock_client_prompt_version_propagated() -> None:
    client = MockAIClient(response="{}")
    result = await client.complete(system="", user="", prompt_version="email_extraction_v2")
    assert result.prompt_version == "email_extraction_v2"


@pytest.mark.asyncio
async def test_mock_client_keyword_routing_purchase() -> None:
    client = MockAIClient()
    result = await client.complete(system="", user="Please purchase 3 monitors")
    import json

    payload = json.loads(result.text)
    assert payload["request_type"] == "purchase_request"


@pytest.mark.asyncio
async def test_mock_client_keyword_routing_issue() -> None:
    client = MockAIClient()
    result = await client.complete(system="", user="HTTP 500 error on billing portal")
    import json

    payload = json.loads(result.text)
    assert payload["request_type"] == "customer_issue"
