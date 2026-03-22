"""Health and observability endpoints.

Three endpoints:
  GET /health        — liveness (is the process up?)
  GET /health/ready  — readiness (DB + AI provider reachable?)
  GET /metrics       — real operational metrics from DB + cost tracker
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.core.logging_config import correlation_id_ctx

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness check — confirms the process is running.

    Returns:
        Dict with status=healthy and a UTC timestamp.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/ready")
def health_ready(request: Request) -> dict:
    """Readiness check — confirms storage and AI provider are accessible.

    Performs two checks:
      storage     — executes a lightweight SELECT against the items table.
      ai_provider — verifies the provider is configured and reachable.
                    For 'mock' this is always ok; for 'anthropic' the API
                    key must be present (no live call is made).

    Returns:
        Dict with status (ready|degraded) and per-component check results.
    """
    storage_status = _check_storage(request)
    ai_status = _check_ai_provider(request)

    all_healthy = storage_status == "ok" and ai_status == "ok"
    overall = "ready" if all_healthy else "degraded"

    logger.info(
        "Readiness check",
        extra={
            "status": overall,
            "storage": storage_status,
            "ai_provider": ai_status,
            "correlation_id": correlation_id_ctx.get(""),
        },
    )
    return {
        "status": overall,
        "checks": {
            "storage": storage_status,
            "ai_provider": ai_status,
        },
    }


@router.get("/metrics")
def metrics(request: Request) -> dict:
    """Real operational metrics sourced from the database and cost tracker.

    Fields:
      processed_today — items created since midnight UTC
      success_rate    — approved / (approved + rejected)
      avg_latency_ms  — mean AI call latency (0 when no calls recorded)
      avg_cost_usd    — mean AI call cost in USD (0 when no calls recorded)
      cost_today_usd  — accumulated AI spend since midnight UTC
      cost_limit_usd  — configured daily cost ceiling (MAX_DAILY_COST_USD)
      queue_depth     — items currently awaiting human review
      items           — full status breakdown counts

    Returns:
        Structured dict with status, data, and metadata.
    """
    storage = request.app.state.storage
    cost_tracker = request.app.state.cost_tracker
    settings = request.app.state.settings
    workflow_service = request.app.state.workflow_service

    db_snapshot = storage.metrics_snapshot()
    item_counts = workflow_service.item_counts()

    logger.info(
        "Metrics requested",
        extra={
            "queue_depth": db_snapshot["queue_depth"],
            "processed_today": db_snapshot["processed_today"],
            "correlation_id": correlation_id_ctx.get(""),
        },
    )

    return {
        "status": "ok",
        "data": {
            "processed_today": db_snapshot["processed_today"],
            "success_rate": db_snapshot["success_rate"],
            "avg_latency_ms": db_snapshot["avg_latency_ms"],
            "avg_cost_usd": db_snapshot["avg_cost_usd"],
            "cost_today_usd": round(cost_tracker.total_today(), 6),
            "cost_limit_usd": settings.max_daily_cost_usd,
            "queue_depth": db_snapshot["queue_depth"],
            "items": item_counts,
        },
        "metadata": {
            "version": "1.0.0",
            "correlation_id": correlation_id_ctx.get(""),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _check_storage(request: Request) -> str:
    """Run a lightweight DB read to confirm storage is accessible.

    Args:
        request: FastAPI request (provides app.state.storage).

    Returns:
        "ok" on success, "error: <detail>" on failure.
    """
    try:
        request.app.state.storage.list_items(status="approved")
        return "ok"
    except Exception as exc:
        logger.warning(
            "Readiness check: storage error",
            extra={"error": str(exc), "correlation_id": correlation_id_ctx.get("")},
        )
        return f"error: {exc}"


def _check_ai_provider(request: Request) -> str:
    """Check that the configured AI provider is reachable.

    For 'mock': always returns ok (no external call needed).
    For 'anthropic': verifies the API key is present (no live call is made
    to avoid latency and cost during readiness polling).

    Args:
        request: FastAPI request (provides app.state.settings).

    Returns:
        "ok" when the provider is ready, "error: <detail>" otherwise.
    """
    settings = request.app.state.settings
    provider = settings.ai_provider

    if provider == "mock":
        return "ok"

    if provider == "anthropic":
        if settings.anthropic_api_key:
            return "ok"
        logger.warning(
            "Readiness check: Anthropic API key not configured",
            extra={"correlation_id": correlation_id_ctx.get("")},
        )
        return "error: anthropic_api_key not set"

    return f"error: unknown provider '{provider}'"
