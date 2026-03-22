"""Health and observability endpoints.

Three endpoints:
  GET /health        — liveness (is the process up?)
  GET /health/ready  — readiness (can the process serve traffic?)
  GET /metrics       — operational item counts and system version
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request

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
    """Readiness check — confirms storage is accessible before serving traffic.

    Returns:
        Dict with status (ready|degraded) and per-component check results.
    """
    try:
        request.app.state.storage.list_items(status="approved")
        storage_status = "ok"
    except Exception as exc:
        logger.warning("Readiness check: storage error", extra={"error": str(exc)})
        storage_status = f"error: {exc}"

    all_healthy = storage_status == "ok"
    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": {"storage": storage_status},
    }


@router.get("/metrics")
def metrics(request: Request) -> dict:
    """Operational metrics — live item counts from storage.

    Returns:
        Dict with item counts by status and system version metadata.
    """
    workflow_service = request.app.state.workflow_service
    return {
        "status": "ok",
        "data": {
            "items": workflow_service.item_counts(),
        },
        "metadata": {"version": "1.0.0"},
    }
