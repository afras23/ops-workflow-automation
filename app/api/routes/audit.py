"""Audit trail routes — read the event history for intake items.

Routes:
  GET /items/{item_id}/audit — ordered event history for an item
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


@router.get("/audit")
def list_all_audit(
    request: Request,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Events per page"),
) -> dict[str, Any]:
    """List all audit events across all items, paginated.

    Args:
        request: FastAPI request.
        page: 1-based page number.
        page_size: Maximum events per page (1–100).

    Returns:
        Dict with events, total, page, and page_size.
    """
    workflow_service = request.app.state.workflow_service
    return workflow_service.get_all_audit_paginated(page=page, page_size=page_size)


@router.get("/items/{item_id}/audit")
def get_item_audit(item_id: str, request: Request) -> list[dict[str, Any]]:
    """Get the ordered audit trail for an intake item.

    Args:
        item_id: The item whose audit log to retrieve.
        request: FastAPI request.

    Returns:
        Ordered list of audit event dicts (oldest first).

    Raises:
        HTTPException 404: If the item does not exist.
    """
    workflow_service = request.app.state.workflow_service
    if not workflow_service.get_item(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return workflow_service.get_audit(item_id)
