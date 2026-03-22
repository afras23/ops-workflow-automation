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

    name: str = Field(description="Sender display name")
    email: EmailStr = Field(description="Sender email address")


class InboxMessage(BaseModel):
    """Validated inbound email message arriving at the API boundary."""

    message_id: str = Field(description="Unique identifier for idempotency deduplication")
    from_: InboxFrom = Field(alias="from", description="Sender identity from the email envelope")
    subject: str = Field(description="Email subject line")
    received_at: datetime = Field(description="ISO 8601 timestamp when the message was received")
    body: str = Field(description="Full email body text")

    model_config = {"populate_by_name": True}


class Requester(BaseModel):
    """Extracted requester identity, always sourced from the message envelope."""

    name: str = Field(description="Requester display name")
    email: EmailStr = Field(description="Requester email address")


class LineItem(BaseModel):
    """A single line item within a purchase request."""

    item: str = Field(description="Item name or description")
    qty: int = Field(ge=1, description="Quantity requested (minimum 1)")
    notes: str | None = Field(default=None, description="Optional notes for this line item")


class Extraction(BaseModel):
    """Fully-enriched extraction result with confidence score.

    Produced by ExtractionService after AI parsing, schema validation,
    and confidence scoring. This is the canonical domain model for an
    extracted intake request.
    """

    request_id: str = Field(description="Stable deterministic ID derived from message envelope")
    request_type: RequestType = Field(description="Classified request type")
    priority: Priority = Field(description="Inferred request priority")
    due_date: str | None = Field(
        default=None, description="Requested due date in YYYY-MM-DD format"
    )
    company: str | None = Field(default=None, description="Requester organisation if identified")
    requester: Requester = Field(description="Requester identity from the email envelope")
    description: str = Field(description="Concise AI-generated summary of the request (≤300 chars)")
    line_items: list[LineItem] = Field(
        default_factory=list,
        description="Explicit line items for purchase requests",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence score in [0, 1]")
    extraction_notes: list[str] = Field(
        default_factory=list,
        description="AI-flagged assumptions, ambiguities, or low-confidence fields",
    )


class AIExtractionOutput(BaseModel):
    """Raw structured output returned by the AI provider before enrichment.

    Missing requester and request_id — those are sourced from the message
    envelope, not the AI, to prevent injection/spoofing.
    """

    request_type: RequestType = Field(description="Classified request type from AI")
    priority: Priority = Field(description="Inferred priority from AI")
    due_date: str | None = Field(
        default=None, description="Due date extracted by AI, YYYY-MM-DD or null"
    )
    company: str | None = Field(default=None, description="Company name extracted by AI, or null")
    description: str = Field(description="AI-generated summary of the request")
    line_items: list[LineItem] = Field(
        default_factory=list,
        description="Line items for purchase requests",
    )
    extraction_notes: list[str] = Field(
        default_factory=list,
        description="AI-reported ambiguities or low-confidence fields",
    )


class IngestResponse(BaseModel):
    """Response from the POST /ingest endpoint."""

    item_id: str = Field(description="Unique item identifier assigned to this intake request")
    status: Status = Field(description="Initial routing status after processing")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence score")
    routed_to: str = Field(
        description="Routing destination: auto_approve, human_review, auto_reject, or idempotent_return"
    )


class ReviewAction(BaseModel):
    """Human reviewer decision submitted to the review endpoint."""

    reviewer: str = Field(description="Identifier of the reviewer (user ID or name)")
    action: Literal["approve", "reject"] = Field(description="Review decision: approve or reject")
    reason: str | None = Field(
        default=None, description="Optional reviewer comments or justification"
    )


class ReviewItem(BaseModel):
    """An intake item as stored and returned by the items API.

    Represents an item in any status; typically used for pending_review queue inspection.
    """

    item_id: str = Field(description="Unique item identifier")
    message_id: str = Field(description="Source email message identifier")
    status: Status = Field(description="Current processing status")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence score")
    extraction: dict = Field(description="Full extraction data as a serialised object")
    created_at: str = Field(description="ISO 8601 creation timestamp")
    updated_at: str = Field(description="ISO 8601 last update timestamp")


# Backward-compatible alias — prefer ReviewItem in new code
StoredItem = ReviewItem
