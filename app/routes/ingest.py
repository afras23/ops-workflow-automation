"""Ingest route.

Accepts inbound messages and passes them to the workflow service.
All routes are prefixed with /api/v1 by the app factory.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models import InboxMessage, IngestResponse

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest(message: InboxMessage, request: Request) -> IngestResponse:
    """Ingest an inbound message and route it through the extraction pipeline."""
    service = request.app.state.workflow_service
    try:
        return await service.ingest(message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
