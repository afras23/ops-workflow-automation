"""Batch processing routes — bulk ingest and progress polling.

Routes:
  POST /batch          — submit a list of emails, returns completed BatchJob
  GET  /batch/{job_id} — retrieve a batch job by ID
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.models.batch import BatchIngestRequest, BatchJob

logger = logging.getLogger(__name__)

router = APIRouter(tags=["batch"])


@router.post("/batch", response_model=BatchJob)
async def create_batch(payload: BatchIngestRequest, request: Request) -> BatchJob:
    """Submit a list of emails for batch processing.

    Processes all emails concurrently. Failures on individual emails
    are isolated — they increment failed_count without aborting the batch.
    Duplicate message_ids are silently deduplicated (counted as succeeded).

    Args:
        payload: List of inbox messages to process.
        request: FastAPI request (provides access to app.state services).

    Returns:
        Completed BatchJob with final progress counters.
    """
    batch_service = request.app.state.batch_service
    batch_job = await batch_service.create_and_run(payload.emails)
    logger.info(
        "POST /batch complete",
        extra={
            "job_id": batch_job.job_id,
            "total": batch_job.total,
            "succeeded": batch_job.succeeded,
            "failed_count": batch_job.failed_count,
        },
    )
    return batch_job


@router.get("/batch/{job_id}", response_model=BatchJob)
def get_batch(job_id: str, request: Request) -> BatchJob:
    """Retrieve a batch job by its ID.

    Args:
        job_id: Batch job identifier returned by POST /batch.
        request: FastAPI request.

    Returns:
        BatchJob with current progress counters.

    Raises:
        HTTPException 404: If no batch job with this ID exists.
    """
    batch_service = request.app.state.batch_service
    batch_job = batch_service.get_job(job_id)
    if not batch_job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return batch_job
