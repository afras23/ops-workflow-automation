"""Pydantic models for audit log entries."""

from __future__ import annotations

from pydantic import BaseModel


class AuditEntry(BaseModel):
    """A single immutable audit log record for an item event."""

    id: int
    item_id: str
    event_type: str
    actor: str
    details: dict
    created_at: str
