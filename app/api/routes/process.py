"""Ingest (process) endpoint — entry point for the AI pipeline.

POST /ingest accepts an InboxMessage, runs it through the extraction
pipeline, and returns a routing decision.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.exceptions import ExtractionError
from app.models.email import InboxMessage, IngestResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["process"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_message(message: InboxMessage, request: Request) -> IngestResponse:
    """Ingest an inbound message and route it through the extraction pipeline.

    Args:
        message: Validated inbox message from the request body.
        request: FastAPI request (used to access app.state.workflow_service).

    Returns:
        IngestResponse with item_id, status, confidence, and routing outcome.

    Raises:
        HTTPException 422: If extraction fails (non-JSON AI response, schema error, etc.).
    """
    workflow_service = request.app.state.workflow_service
    try:
        return await workflow_service.ingest(message)
    except ExtractionError as exc:
        logger.warning(
            "Ingest rejected — extraction error",
            extra={"error": exc.message, "context": exc.context},
        )
        raise HTTPException(status_code=422, detail=exc.message) from exc
