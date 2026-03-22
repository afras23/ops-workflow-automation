"""AI client with cost tracking, retry, and circuit breaker.

Four components:
- AICallResult      — Pydantic result model (text, tokens, cost, latency)
- DailyCostTracker  — Accumulates USD cost per calendar day, enforces daily limit
- CircuitBreaker    — Opens after N failures in a rolling time window
- AIClient / MockAIClient / AnthropicClient — Provider abstraction

Use get_ai_client(settings, cost_tracker, circuit_breaker) at startup.
The cost_tracker and circuit_breaker should be singletons shared across requests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel

from app.config import Settings
from app.core.constants import (
    AI_MAX_TOKENS,
    CLAUDE_SONNET_INPUT_COST_PER_1M,
    CLAUDE_SONNET_OUTPUT_COST_PER_1M,
)
from app.core.exceptions import CostLimitExceeded, RetryableError
from app.core.logging_config import correlation_id_ctx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class AICallResult(BaseModel):
    """Structured result of a single AI completion call."""

    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    model: str
    prompt_version: str


# ---------------------------------------------------------------------------
# Mock payloads (used by MockAIClient)
# ---------------------------------------------------------------------------

_MOCK_PURCHASE: dict[str, Any] = {
    "request_type": "purchase_request",
    "priority": "high",
    "due_date": "2026-03-31",
    "company": "Acme Corp",
    "description": "Purchase request for 2x ThinkPad T14s laptops for the engineering team.",
    "line_items": [{"item": "ThinkPad T14s", "qty": 2}],
    "extraction_notes": ["mock extraction — purchase_request keyword matched"],
}

_MOCK_ISSUE: dict[str, Any] = {
    "request_type": "customer_issue",
    "priority": "urgent",
    "due_date": None,
    "company": "Northwind Traders",
    "description": "Customer reporting HTTP 500 error on billing portal. Cannot access invoices.",
    "line_items": [],
    "extraction_notes": ["mock extraction — customer_issue keyword matched"],
}

_MOCK_OPS: dict[str, Any] = {
    "request_type": "ops_change",
    "priority": "medium",
    "due_date": None,
    "company": None,
    "description": "Request to update deployment configuration for the staging environment.",
    "line_items": [],
    "extraction_notes": ["mock extraction — ops_change keyword matched"],
}

_MOCK_VAGUE: dict[str, Any] = {
    "request_type": "other",
    "priority": "medium",
    "due_date": None,
    "company": None,
    "description": "Unclassified request with insufficient context.",
    "line_items": [],
    "extraction_notes": ["mock extraction — no keyword match, low confidence expected"],
}


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


class DailyCostTracker:
    """Accumulates AI API spend per calendar day (UTC) and enforces a daily limit.

    Resets automatically at UTC midnight. Not thread-safe for concurrent writes,
    but safe for the single-process async use case.
    """

    def __init__(self) -> None:
        """Initialise with zero cost for today."""
        self._date: date = datetime.now(UTC).date()
        self._total_usd: float = 0.0

    def add(self, cost_usd: float) -> None:
        """Add cost_usd to today's running total, resetting if the date changed.

        Args:
            cost_usd: Cost in USD to record for this call.
        """
        today = datetime.now(UTC).date()
        if today != self._date:
            self._date = today
            self._total_usd = 0.0
        self._total_usd += cost_usd

    def total_today(self) -> float:
        """Return accumulated cost since midnight UTC, zero if date has rolled over.

        Returns:
            Total USD spent today.
        """
        if datetime.now(UTC).date() != self._date:
            return 0.0
        return self._total_usd

    def check_limit(self, limit_usd: float) -> None:
        """Raise CostLimitExceeded if today's total has reached the configured limit.

        Args:
            limit_usd: Maximum permitted daily spend in USD.

        Raises:
            CostLimitExceeded: When total_today() >= limit_usd.
        """
        total = self.total_today()
        if total >= limit_usd:
            raise CostLimitExceeded(
                f"Daily cost limit ${limit_usd:.2f} exceeded (used: ${total:.4f})",
                context={"total_usd": total, "limit_usd": limit_usd},
            )


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Opens after failure_threshold failures within a rolling window_seconds window.

    When open, callers should skip the AI call and surface a RetryableError
    rather than hammering a failing provider.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
    ) -> None:
        """Initialise with threshold and time window.

        Args:
            failure_threshold: Number of failures within the window to open the circuit.
            window_seconds: Rolling window length in seconds.
        """
        self._threshold = failure_threshold
        self._window = window_seconds
        self._failures: deque[float] = deque()

    def record_success(self) -> None:
        """Clear all failure records — circuit closes immediately."""
        self._failures.clear()

    def record_failure(self) -> None:
        """Record a failure timestamp and prune stale entries outside the window."""
        now = time.monotonic()
        self._failures.append(now)
        self._prune(now)

    def is_open(self) -> bool:
        """Return True if too many recent failures have triggered the open state.

        Returns:
            True when failure count within the window >= failure_threshold.
        """
        self._prune(time.monotonic())
        return len(self._failures) >= self._threshold

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()


# ---------------------------------------------------------------------------
# AI client abstraction
# ---------------------------------------------------------------------------


class AIClient(ABC):
    """Protocol for AI completion providers."""

    @abstractmethod
    async def complete(
        self, system: str, user: str, *, prompt_version: str = ""
    ) -> AICallResult:
        """Send a prompt and return a structured result.

        Args:
            system: System prompt describing the AI's role and output format.
            user: User-turn message containing the data to process.
            prompt_version: Version tag embedded in the result for audit logging.

        Returns:
            AICallResult with text, token counts, cost, and latency.
        """


class MockAIClient(AIClient):
    """Returns canned AICallResult responses based on keyword matching.

    Used in tests and local development to avoid real API calls.
    """

    def __init__(self, response: str | None = None) -> None:
        """Initialise with an optional fixed response string.

        Args:
            response: If set, always return this text regardless of input keywords.
        """
        self._fixed_response = response

    async def complete(
        self, system: str, user: str, *, prompt_version: str = ""
    ) -> AICallResult:
        """Return a canned result matched to keywords in the user prompt.

        Args:
            system: Ignored in mock mode.
            user: Inspected for keyword signals to choose a canned response.
            prompt_version: Passed through to AICallResult.

        Returns:
            AICallResult with mock text, zero tokens, and zero cost.
        """
        if self._fixed_response is not None:
            response_text = self._fixed_response
        else:
            lower = user.lower()
            if any(kw in lower for kw in ("purchase", "order", "item:", "buy", "procure")):
                payload = _MOCK_PURCHASE
            elif any(kw in lower for kw in ("error", "issue", "billing", "incident", "500", "bug")):
                payload = _MOCK_ISSUE
            elif any(kw in lower for kw in ("change", "update", "deploy", "config")):
                payload = _MOCK_OPS
            else:
                payload = _MOCK_VAGUE
            response_text = json.dumps(payload)
            logger.debug(
                "MockAIClient returning canned response",
                extra={"request_type": payload["request_type"]},
            )

        return AICallResult(
            text=response_text,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            latency_ms=0.0,
            model="mock",
            prompt_version=prompt_version,
        )


class AnthropicClient(AIClient):
    """Claude API client with retry, circuit breaker, and cost tracking."""

    def __init__(
        self,
        api_key: str,
        model: str,
        cost_tracker: DailyCostTracker,
        circuit_breaker: CircuitBreaker,
        max_daily_cost_usd: float,
    ) -> None:
        """Initialise with API credentials and shared control objects.

        Args:
            api_key: Anthropic API key.
            model: Model identifier (e.g. claude-sonnet-4-6).
            cost_tracker: Shared daily cost accumulator.
            circuit_breaker: Shared failure-tracking circuit breaker.
            max_daily_cost_usd: Refuse new calls when this daily limit is reached.
        """
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._cost_tracker = cost_tracker
        self._circuit_breaker = circuit_breaker
        self._max_daily_cost = max_daily_cost_usd

    async def complete(
        self, system: str, user: str, *, prompt_version: str = ""
    ) -> AICallResult:
        """Call Claude with cost-limit check, circuit-breaker guard, and retry.

        Args:
            system: System prompt.
            user: User-turn message.
            prompt_version: Prompt version tag embedded in the result.

        Returns:
            AICallResult with real token counts, cost, and latency.

        Raises:
            CostLimitExceeded: If the daily budget is exhausted.
            RetryableError: If the circuit breaker is open.
            TimeoutError | ConnectionError | OSError: If all retry attempts fail.
        """
        self._cost_tracker.check_limit(self._max_daily_cost)

        if self._circuit_breaker.is_open():
            raise RetryableError(
                "Circuit breaker open — AI provider temporarily unavailable",
                context={"model": self._model},
            )

        ai_result = await _call_with_retry(
            lambda: self._raw_complete(system, user, prompt_version=prompt_version),
            circuit_breaker=self._circuit_breaker,
        )
        self._cost_tracker.add(ai_result.cost_usd)
        self._circuit_breaker.record_success()

        logger.info(
            "AI call complete",
            extra={
                "model": ai_result.model,
                "tokens_in": ai_result.tokens_in,
                "tokens_out": ai_result.tokens_out,
                "cost_usd": ai_result.cost_usd,
                "latency_ms": round(ai_result.latency_ms, 1),
                "prompt_version": prompt_version,
                "correlation_id": correlation_id_ctx.get(""),
            },
        )
        return ai_result

    async def _raw_complete(
        self, system: str, user: str, *, prompt_version: str
    ) -> AICallResult:
        """Single raw API call with token counting and cost calculation.

        Args:
            system: System prompt.
            user: User-turn message.
            prompt_version: Embedded in the returned result.

        Returns:
            AICallResult with real token counts, computed cost, and measured latency.
        """
        start = time.monotonic()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=AI_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        latency_ms = (time.monotonic() - start) * 1000

        tokens_in: int = response.usage.input_tokens
        tokens_out: int = response.usage.output_tokens
        cost_usd = (
            tokens_in * CLAUDE_SONNET_INPUT_COST_PER_1M / 1_000_000
            + tokens_out * CLAUDE_SONNET_OUTPUT_COST_PER_1M / 1_000_000
        )

        return AICallResult(
            text=response.content[0].text,  # type: ignore[union-attr]
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            model=self._model,
            prompt_version=prompt_version,
        )


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


async def _call_with_retry(
    call_fn: Callable[[], Awaitable[AICallResult]],
    *,
    circuit_breaker: CircuitBreaker | None = None,
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> AICallResult:
    """Retry call_fn on transient errors with exponential backoff and jitter.

    Args:
        call_fn: Async no-arg callable returning AICallResult.
        circuit_breaker: If provided, record_failure() is called on each transient error.
        max_attempts: Maximum total attempts before re-raising the last exception.
        base_delay: Base wait in seconds; doubles each retry with ±0.5s random jitter.

    Returns:
        AICallResult from the first successful attempt.

    Raises:
        The last transient exception if all attempts are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await call_fn()
        except (TimeoutError, ConnectionError, OSError) as exc:
            last_exc = exc
            if circuit_breaker is not None:
                circuit_breaker.record_failure()
            if attempt < max_attempts - 1:
                delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "AI call failed, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "delay_s": round(delay, 2),
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_ai_client(
    settings: Settings,
    cost_tracker: DailyCostTracker | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> AIClient:
    """Return the appropriate AI client for the current configuration.

    Args:
        settings: Application settings; inspects ai_provider and anthropic_api_key.
        cost_tracker: Optional shared tracker (created if not provided).
        circuit_breaker: Optional shared circuit breaker (created if not provided).

    Returns:
        AnthropicClient if provider is "anthropic" and a key is set, else MockAIClient.
    """
    if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
        tracker = cost_tracker or DailyCostTracker()
        breaker = circuit_breaker or CircuitBreaker()
        logger.info("Using AnthropicClient", extra={"model": settings.ai_model})
        return AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.ai_model,
            cost_tracker=tracker,
            circuit_breaker=breaker,
            max_daily_cost_usd=settings.max_daily_cost_usd,
        )

    logger.info("Using MockAIClient", extra={"ai_provider": settings.ai_provider})
    return MockAIClient()
