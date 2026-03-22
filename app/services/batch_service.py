"""Batch ingest service.

Accepts a list of emails, creates a persistent batch job record, and
processes each email concurrently via asyncio.gather. Progress counters
(processed, succeeded, failed_count) are updated atomically after each
email so GET /batch/{id} reflects live progress.

Error isolation: ExtractionError on a single email increments failed_count
and does not abort the rest of the batch.

Idempotency: WorkflowService.ingest() deduplicates by message_id. Emails
with a previously-seen message_id return an idempotent_return result that
is counted as succeeded (not a new extraction, but not an error either).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app.core.exceptions import ExtractionError
from app.models.batch import BatchJob
from app.models.email import InboxMessage
from app.storage import Storage

logger = logging.getLogger(__name__)


class BatchService:
    """Orchestrates bulk email ingest with per-email error isolation."""

    def __init__(self, storage: Storage, workflow_service: Any) -> None:
        """Initialise with storage and the workflow service.

        Args:
            storage: SQLite storage backend for batch job records.
            workflow_service: WorkflowService for per-email ingest.
        """
        self._storage = storage
        self._workflow = workflow_service

    async def create_and_run(self, emails: list[InboxMessage]) -> BatchJob:
        """Create a batch job and process all emails concurrently.

        Each email is processed in a separate asyncio task. Failures are
        isolated: one bad email increments failed_count without aborting
        the remaining work. The job status is set to 'complete' when all
        tasks finish, regardless of individual failures.

        Args:
            emails: Non-empty list of inbox messages to process.

        Returns:
            Completed BatchJob with final progress counters.
        """
        job_id = str(uuid.uuid4())
        self._storage.create_batch_job(job_id, total=len(emails))
        logger.info(
            "Batch job created",
            extra={"job_id": job_id, "total": len(emails)},
        )

        await asyncio.gather(*[self._process_one(job_id, email) for email in emails])

        self._storage.finalize_batch_job(job_id)
        batch_job = self._get_job_or_raise(job_id)
        logger.info(
            "Batch job complete",
            extra={
                "job_id": job_id,
                "succeeded": batch_job.succeeded,
                "failed_count": batch_job.failed_count,
            },
        )
        return batch_job

    def get_job(self, job_id: str) -> BatchJob | None:
        """Return a batch job by ID, or None if not found.

        Args:
            job_id: Batch job identifier.

        Returns:
            BatchJob model, or None if not found.
        """
        row = self._storage.get_batch_job(job_id)
        if not row:
            return None
        return _row_to_batch_job(row)

    async def _process_one(self, job_id: str, email: InboxMessage) -> None:
        """Process a single email and update batch progress atomically.

        Catches ExtractionError so one failure does not abort the batch.
        All other exceptions are re-raised after marking the email as failed.

        Args:
            job_id: Batch job to update on completion.
            email: Inbox message to ingest.
        """
        try:
            await self._workflow.ingest(email)
            self._storage.increment_batch_result(job_id, succeeded=True)
            logger.debug(
                "Batch email succeeded",
                extra={"job_id": job_id, "message_id": email.message_id},
            )
        except ExtractionError as exc:
            self._storage.increment_batch_result(job_id, succeeded=False)
            logger.warning(
                "Batch email failed — extraction error",
                extra={"job_id": job_id, "message_id": email.message_id, "error": str(exc)},
            )

    def _get_job_or_raise(self, job_id: str) -> BatchJob:
        """Return a BatchJob or raise RuntimeError if absent (should never happen).

        Args:
            job_id: Batch job identifier.

        Returns:
            BatchJob model.

        Raises:
            RuntimeError: If the job was lost between create and finalize.
        """
        row = self._storage.get_batch_job(job_id)
        if not row:
            raise RuntimeError(f"Batch job {job_id!r} missing after creation")
        return _row_to_batch_job(row)


def _row_to_batch_job(row: dict) -> BatchJob:
    """Convert a raw storage row to a BatchJob model.

    Args:
        row: Dict from Storage.get_batch_job().

    Returns:
        Validated BatchJob model.
    """
    return BatchJob(
        job_id=row["job_id"],
        status=row["status"],
        total=row["total"],
        processed=row["processed"],
        succeeded=row["succeeded"],
        failed_count=row["failed_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
