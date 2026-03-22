"""Pydantic data models for email intake messages and extraction results.

These models validate all data crossing the API and service boundaries.
No raw dicts should flow between layers — always use these models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

RequestType = Literal[
    "purchase_request", "customer_issue", "ops_change", "general_inquiry", "other"
]
Priority = Literal["low", "medium", "high", "urgent"]
Status = Literal["pending_review", "approved", "rejected", "failed"]


class InboxFrom(BaseModel):
    """Sender identity extracted from the email envelope."""

    name: str
    email: EmailStr


class InboxMessage(BaseModel):
    """Validated inbound email message arriving at the API boundary."""

    message_id: str
    from_: InboxFrom = Field(alias="from")
    subject: str
    received_at: datetime
    body: str

    model_config = {"populate_by_name": True}


class Requester(BaseModel):
    """Extracted requester identity, always sourced from the message envelope."""

    name: str
    email: EmailStr


class LineItem(BaseModel):
    """A single line item within a purchase request."""

    item: str
    qty: int = Field(ge=1)
    notes: str | None = None


class Extraction(BaseModel):
    """Fully-enriched extraction result with confidence score.

    Produced by ExtractionService after AI parsing, schema validation,
    and confidence scoring. This is the canonical domain model for an
    extracted intake request.
    """

    request_id: str
    request_type: RequestType
    priority: Priority
    due_date: str | None = None
    company: str | None = None
    requester: Requester
    description: str
    line_items: list[LineItem] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    extraction_notes: list[str] = Field(default_factory=list)


class AIExtractionOutput(BaseModel):
    """Raw structured output returned by the AI provider before enrichment.

    Missing requester and request_id — those are sourced from the message
    envelope, not the AI, to prevent injection/spoofing.
    """

    request_type: RequestType
    priority: Priority
    due_date: str | None = None
    company: str | None = None
    description: str
    line_items: list[LineItem] = Field(default_factory=list)
    extraction_notes: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    """Response from the POST /ingest endpoint."""

    item_id: str
    status: Status
    confidence: float
    routed_to: str


class ReviewAction(BaseModel):
    """Human reviewer decision submitted to the review endpoint."""

    reviewer: str
    action: Literal["approve", "reject"]
    reason: str | None = None


class StoredItem(BaseModel):
    """Serialised item as returned from the database layer."""

    item_id: str
    message_id: str
    status: Status
    confidence: float
    extraction: dict
    created_at: str
    updated_at: str
