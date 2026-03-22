"""Custom exception hierarchy for the ops workflow application.

All app errors carry status_code, error_code, message, and a context dict
so that the error middleware can produce consistent structured responses.
"""

from __future__ import annotations


class BaseAppError(Exception):
    """Base class for all application-level errors.

    Args:
        message: Human-readable error description.
        context: Optional dict of structured context for logging and responses.
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        context: dict | None = None,
    ) -> None:
        """Initialise with a message and optional structured context."""
        super().__init__(message)
        self.message = message
        self.context: dict = context or {}


class ExtractionError(BaseAppError):
    """Raised when AI extraction fails or returns invalid output.

    Covers: provider unavailability, non-JSON responses, schema mismatches.
    """

    status_code = 422
    error_code = "extraction_failed"


class RoutingError(BaseAppError):
    """Raised when routing cannot determine a valid action for an item."""

    status_code = 500
    error_code = "routing_failed"


class AppValidationError(BaseAppError):
    """Raised when input validation fails at the application boundary."""

    status_code = 400
    error_code = "validation_failed"


class CostLimitExceeded(BaseAppError):
    """Raised when the daily AI cost budget is exhausted.

    The system should degrade gracefully: refuse new AI requests, don't crash.
    """

    status_code = 429
    error_code = "cost_limit_exceeded"


class RateLimitExceeded(BaseAppError):
    """Raised when an upstream provider rate-limits this service.

    Args:
        message: Error description.
        retry_after: Seconds the caller should wait before retrying.
        context: Optional structured context.
    """

    status_code = 429
    error_code = "rate_limit_exceeded"

    def __init__(
        self,
        message: str = "Rate limited by upstream provider",
        *,
        retry_after: float = 60.0,
        context: dict | None = None,
    ) -> None:
        """Initialise with a retry_after hint."""
        super().__init__(message, context=context)
        self.retry_after = retry_after


class RetryableError(BaseAppError):
    """Raised on transient failures that are safe to retry with backoff."""

    status_code = 503
    error_code = "service_unavailable"
