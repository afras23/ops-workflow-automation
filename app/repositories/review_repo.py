"""Review queue repository — data access for items awaiting human review.

Thin wrapper around EmailRepository that narrows reads to pending_review
items. Write operations (approve/reject) go through EmailRepository directly.
"""

from __future__ import annotations

import logging
from typing import Any

from app.repositories.email_repo import EmailRepository

logger = logging.getLogger(__name__)


class ReviewRepository:
    """Data access layer for the human review queue."""

    def __init__(self, email_repo: EmailRepository) -> None:
        """Initialise with an EmailRepository.

        Args:
            email_repo: Underlying item repository.
        """
        self._email_repo = email_repo

    def list_pending(self) -> list[dict[str, Any]]:
        """Return all items currently awaiting human review.

        Returns:
            List of raw item dicts with status=pending_review.
        """
        return self._email_repo.list_items(status="pending_review")

    def list_pending_paginated(self, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        """Return a page of pending_review items with total count.

        Args:
            page: 1-based page number.
            page_size: Maximum items per page.

        Returns:
            Tuple of (item dicts for this page, total pending count).
        """
        return self._email_repo.list_items_paginated(page, page_size, status="pending_review")

    def get_reviewable_item(self, item_id: str) -> dict[str, Any] | None:
        """Return an item only if it exists and is in pending_review status.

        Args:
            item_id: The item to look up.

        Returns:
            Raw item dict if reviewable, None otherwise.
        """
        stored_item = self._email_repo.get_item(item_id)
        if stored_item and stored_item["status"] == "pending_review":
            return stored_item
        return None
