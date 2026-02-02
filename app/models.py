from __future__ import annotations

from pydantic import BaseModel, Field, EmailStr
from typing import Literal, Optional
from datetime import datetime

RequestType = Literal["purchase_request", "customer_issue", "ops_change", "general_inquiry", "other"]
Priority = Literal["low", "medium", "high", "urgent"]
Status = Literal["pending_review", "approved", "rejected", "failed"]

class InboxFrom(BaseModel):
    name: str
    email: EmailStr

class InboxMessage(BaseModel):
    message_id: str
    from_: InboxFrom = Field(alias="from")
    subject: str
    received_at: datetime
    body: str

class Requester(BaseModel):
    name: str
    email: EmailStr

class LineItem(BaseModel):
    item: str
    qty: int = Field(ge=1)
    notes: Optional[str] = None

class Extraction(BaseModel):
    request_id: str
    request_type: RequestType
    priority: Priority
    due_date: Optional[str] = None  # ISO date YYYY-MM-DD
    company: Optional[str] = None
    requester: Requester
    description: str
    line_items: list[LineItem] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    extraction_notes: list[str] = Field(default_factory=list)

class IngestResponse(BaseModel):
    item_id: str
    status: Status
    confidence: float
    routed_to: str

class ReviewAction(BaseModel):
    reviewer: str
    action: Literal["approve", "reject"]
    reason: Optional[str] = None

class StoredItem(BaseModel):
    item_id: str
    message_id: str
    status: Status
    confidence: float
    extraction: dict
    created_at: str
    updated_at: str
