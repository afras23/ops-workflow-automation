"""Health and metrics routes.

Provides liveness, readiness, and operational metrics endpoints.
All routes are prefixed with /api/v1 by the app factory.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness check — confirms the process is running."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready")
def health_ready(request: Request) -> dict:
    """Readiness check — confirms storage is accessible."""
    try:
        # A lightweight probe: list with limit equivalent (list returns all, but it's SQLite so fine)
        request.app.state.storage.list_items(status="approved")
        storage_status = "ok"
    except Exception as exc:
        storage_status = f"error: {exc}"

    all_ok = storage_status == "ok"
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": {"storage": storage_status},
    }


@router.get("/metrics")
def metrics(request: Request) -> dict:
    """Operational metrics — live item counts from storage."""
    service = request.app.state.workflow_service
    return {
        "items": service.item_counts(),
        "system": {"version": "1.0.0"},
    }
