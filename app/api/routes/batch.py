"""Batch processing routes — bulk ingest and status polling.

Placeholder for future batch operations. Currently exposes a stub
endpoint to confirm the route is registered and healthy.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["batch"])


@router.get("/batch/status")
def batch_status() -> dict:
    """Batch processing status — placeholder endpoint.

    Returns:
        Dict confirming the batch route is available.
    """
    return {"status": "ok", "message": "Batch processing not yet implemented"}
