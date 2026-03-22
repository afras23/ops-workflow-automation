"""Pydantic models for audit log entries."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    """A single immutable audit log record for an item event."""

    id: int = Field(description="Auto-incremented audit log row ID")
    item_id: str = Field(description="Intake item this event belongs to")
    event_type: str = Field(description="Event type identifier, e.g. ingested, approved, rejected")
    actor: str = Field(description="Actor who triggered the event: reviewer ID or 'system'")
    details: dict = Field(description="Structured event details — schema varies by event_type")
    created_at: str = Field(description="ISO 8601 timestamp when this event was recorded")
