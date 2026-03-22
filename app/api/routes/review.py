"""Review queue routes — list items and submit review decisions.

Routes:
  GET  /items                    — list all items (filterable by status)
  GET  /items/{item_id}          — get full item detail
  POST /items/{item_id}/review   — apply a human approve/reject decision
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.models.email import ReviewAction

logger = logging.getLogger(__name__)

router = APIRouter(tags=["review"])


@router.get("/items")
def list_items(
    request: Request,
    status: str | None = Query(default=None, description="Filter by status"),
) -> list[dict[str, Any]]:
    """List all intake items, optionally filtered by status.

    Args:
        request: FastAPI request.
        status: Optional status filter (approved, pending_review, rejected, failed).

    Returns:
        List of item summary dicts.
    """
    workflow_service = request.app.state.workflow_service
    return workflow_service.list_items(status=status)


@router.get("/items/{item_id}")
def get_item(item_id: str, request: Request) -> dict[str, Any]:
    """Get full detail for a single intake item.

    Args:
        item_id: Stable item identifier.
        request: FastAPI request.

    Returns:
        Full item detail dict.

    Raises:
        HTTPException 404: If the item does not exist.
    """
    workflow_service = request.app.state.workflow_service
    stored_item = workflow_service.get_item(item_id)
    if not stored_item:
        raise HTTPException(status_code=404, detail="Item not found")
    return stored_item


@router.post("/items/{item_id}/review")
async def review_item(
    item_id: str,
    action: ReviewAction,
    request: Request,
) -> JSONResponse:
    """Apply a human review decision (approve or reject) to a pending item.

    Args:
        item_id: The item to review.
        action: Decision containing reviewer name, action, and optional reason.
        request: FastAPI request.

    Returns:
        JSON response with ok=True and the resulting status.

    Raises:
        HTTPException 404: If the item does not exist.
        HTTPException 400: If the item is not in pending_review status.
    """
    workflow_service = request.app.state.workflow_service
    review_service = request.app.state.review_service

    stored_item = workflow_service.get_item(item_id)
    if not stored_item:
        raise HTTPException(status_code=404, detail="Item not found")
    if stored_item["status"] != "pending_review":
        raise HTTPException(
            status_code=400,
            detail=f"Item not reviewable (current status: {stored_item['status']})",
        )

    decision_result = await review_service.handle_review(item_id, action)
    return JSONResponse(decision_result)
