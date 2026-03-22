"""Audit log repository — data access for audit trail entries.

All audit writes and reads from the service layer go through this
repository, not Storage directly.
"""

from __future__ import annotations

import logging
from typing import Any

from app.storage import Storage

logger = logging.getLogger(__name__)


class AuditRepository:
    """Data access layer for audit log entries."""

    def __init__(self, storage: Storage) -> None:
        """Initialise with a Storage instance.

        Args:
            storage: Underlying SQLite storage backend.
        """
        self._storage = storage

    def write_event(
        self,
        item_id: str,
        event_type: str,
        actor: str,
        details: dict[str, Any],
    ) -> None:
        """Persist an audit event to the log.

        Args:
            item_id: The item this event belongs to.
            event_type: Identifier for the event kind (e.g. "ingested").
            actor: Who caused the event ("system" or reviewer username).
            details: Structured event-specific context.
        """
        self._storage.write_audit(item_id, event_type, actor, details)

    def list_events(self, item_id: str) -> list[dict[str, Any]]:
        """Return all audit events for an item ordered by creation time.

        Args:
            item_id: The item whose events to retrieve.

        Returns:
            List of raw audit dicts in chronological order.
        """
        return self._storage.list_audit(item_id)
