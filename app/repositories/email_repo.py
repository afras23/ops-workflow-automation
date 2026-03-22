"""Email item repository — data access for intake items.

Wraps the SQLite Storage class. All item reads and writes from the
service layer go through this repository, not Storage directly.
"""

from __future__ import annotations

import logging
from typing import Any

from app.storage import Storage

logger = logging.getLogger(__name__)


class EmailRepository:
    """Data access layer for email intake items."""

    def __init__(self, storage: Storage) -> None:
        """Initialise with a Storage instance.

        Args:
            storage: Underlying SQLite storage backend.
        """
        self._storage = storage

    def get_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        """Return a stored item by its idempotency key, or None if absent.

        Args:
            message_id: The unique message identifier used for deduplication.

        Returns:
            Raw item dict, or None if not found.
        """
        return self._storage.get_by_message_id(message_id)

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        """Return full item detail by item_id, or None if not found.

        Args:
            item_id: The stable item identifier.

        Returns:
            Raw item dict, or None if not found.
        """
        return self._storage.get_item(item_id)

    def list_items(self, *, status: str | None = None) -> list[dict[str, Any]]:
        """Return all items, optionally filtered by status.

        Args:
            status: Optional status filter (approved, pending_review, etc.).

        Returns:
            List of raw item dicts ordered by created_at descending.
        """
        return self._storage.list_items(status=status)

    def create_item(
        self,
        *,
        item_id: str,
        message_id: str,
        status: str,
        confidence: float,
        extraction: dict,
    ) -> None:
        """Persist a new intake item to storage.

        Args:
            item_id: Stable item identifier.
            message_id: Source message identifier (idempotency key).
            status: Initial routing status.
            confidence: Extraction confidence score.
            extraction: Serialisable extraction dict.
        """
        self._storage.create_item(
            item_id=item_id,
            message_id=message_id,
            status=status,
            confidence=confidence,
            extraction=extraction,
        )
        logger.debug("Item created", extra={"item_id": item_id, "status": status})

    def list_items_paginated(
        self, page: int, page_size: int, *, status: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a page of items and the total matching count.

        Args:
            page: 1-based page number.
            page_size: Maximum items to return per page.
            status: Optional status filter.

        Returns:
            Tuple of (item dicts for this page, total matching count).
        """
        return self._storage.list_items_paginated(page, page_size, status=status)

    def update_status(self, item_id: str, status: str) -> None:
        """Update the routing status of an existing item.

        Args:
            item_id: The item to update.
            status: The new status value.
        """
        self._storage.update_status(item_id, status)
        logger.debug("Item status updated", extra={"item_id": item_id, "status": status})
