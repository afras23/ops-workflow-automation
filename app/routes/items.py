"""Items routes.

CRUD and review endpoints for processed inbox items.
All routes are prefixed with /api/v1 by the app factory.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.models import ReviewAction

router = APIRouter(tags=["items"])


@router.get("/items")
def list_items(request: Request, status: str | None = Query(default=None)) -> list:
    """List all items, optionally filtered by status."""
    service = request.app.state.workflow_service
    return service.list_items(status=status)


@router.get("/items/{item_id}")
def get_item(item_id: str, request: Request) -> dict:
    """Get full detail for a single item."""
    service = request.app.state.workflow_service
    item = service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item


@router.get("/items/{item_id}/audit")
def get_audit(item_id: str, request: Request) -> list:
    """Get the ordered audit trail for an item."""
    service = request.app.state.workflow_service
    if not service.get_item(item_id):
        raise HTTPException(status_code=404, detail="Not found")
    return service.get_audit(item_id)


@router.post("/items/{item_id}/review")
async def review_item(item_id: str, action: ReviewAction, request: Request) -> JSONResponse:
    """Apply a human review decision (approve or reject) to a pending item."""
    service = request.app.state.workflow_service
    item = service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item["status"] != "pending_review":
        raise HTTPException(
            status_code=400,
            detail=f"Item not in pending_review (current={item['status']})",
        )
    result = await service.handle_review(item_id, action)
    return JSONResponse(result)
