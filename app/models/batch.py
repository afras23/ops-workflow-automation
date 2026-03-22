"""Pydantic models for batch ingest jobs.

BatchIngestRequest  — POST /batch request body (list of emails)
BatchJob            — Persistent batch job record with progress counters
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.email import InboxMessage


class BatchIngestRequest(BaseModel):
    """Request body for POST /batch.

    Contains a list of inbox messages to process as a single batch job.
    """

    emails: list[InboxMessage] = Field(
        min_length=1,
        description="Non-empty list of inbox messages to process in this batch",
    )


class BatchJob(BaseModel):
    """Persistent batch job record returned by GET /batch/{job_id}.

    Progress counters (processed, succeeded, failed_count) are updated
    atomically as each email completes so GET can be polled for live progress.
    """

    job_id: str = Field(description="Unique batch job identifier")
    status: str = Field(description="Job lifecycle status: running | complete | failed")
    total: int = Field(ge=0, description="Total number of emails submitted in this batch")
    processed: int = Field(ge=0, description="Emails processed so far (succeeded + failed)")
    succeeded: int = Field(ge=0, description="Emails that completed without error")
    failed_count: int = Field(ge=0, description="Emails that raised an error during processing")
    created_at: str = Field(description="ISO 8601 timestamp when the job was created")
    updated_at: str = Field(description="ISO 8601 timestamp of the last progress update")
