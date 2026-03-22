"""Review service — processes human review decisions for pending items.

Applies approve/reject decisions, updates status, writes audit events,
and dispatches approved items to downstream destinations (CRM, Slack).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import Settings
from app.core.constants import (
    ACTOR_SYSTEM,
    EVENT_APPROVED,
    EVENT_DESTINATIONS_WRITTEN,
    EVENT_REJECTED,
    EVENT_SLACK_NOTIFIED,
)
from app.integrations.crm_client import append_airtable_row, append_sheet_row
from app.integrations.slack_client import send_slack_summary
from app.models.email import ReviewAction, ReviewItem
from app.repositories.email_repo import EmailRepository
from app.repositories.review_repo import ReviewRepository
from app.storage import Storage
from app.utils import redact_pii

logger = logging.getLogger(__name__)


class ReviewService:
    """Processes human review decisions for pending intake items."""

    def __init__(self, storage: Storage, settings: Settings) -> None:
        """Initialise with storage and settings.

        Args:
            storage: SQLite storage backend for status updates and audit writes.
            settings: Application settings for destination paths and Slack URL.
        """
        self._storage = storage
        self._settings = settings
        self._review_repo = ReviewRepository(email_repo=EmailRepository(storage))

    def get_pending_items(self, page: int, page_size: int) -> dict[str, Any]:
        """Return a paginated list of items awaiting human review.

        Args:
            page: 1-based page number.
            page_size: Maximum items per page.

        Returns:
            Dict with items list, total count, page, and page_size.
        """
        raw_rows, total = self._review_repo.list_pending_paginated(page, page_size)
        review_items = [
            ReviewItem(
                item_id=row["item_id"],
                message_id=row["message_id"],
                status=row["status"],
                confidence=row["confidence"],
                extraction=json.loads(row["extraction_json"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            ).model_dump()
            for row in raw_rows
        ]
        return {
            "items": review_items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def handle_review(self, item_id: str, action: ReviewAction) -> dict[str, Any]:
        """Apply a human review decision to a pending item.

        Args:
            item_id: ID of the pending_review item.
            action: Decision containing reviewer name, approve/reject, and optional reason.

        Returns:
            Dict with ok=True and the resulting status string.
        """
        if action.action == "reject":
            return self._apply_rejection(item_id, action)

        return await self._apply_approval(item_id, action)

    def _apply_rejection(self, item_id: str, action: ReviewAction) -> dict[str, Any]:
        """Reject an item and write an audit event.

        Args:
            item_id: The item to reject.
            action: Review decision with reviewer and optional reason.

        Returns:
            Dict with ok=True and status=rejected.
        """
        self._storage.update_status(item_id, "rejected")
        self._storage.write_audit(
            item_id,
            EVENT_REJECTED,
            action.reviewer,
            {"reason": action.reason or ""},
        )
        logger.info(
            "Item rejected by reviewer",
            extra={"item_id": item_id, "reviewer": action.reviewer},
        )
        return {"ok": True, "status": "rejected"}

    async def _apply_approval(self, item_id: str, action: ReviewAction) -> dict[str, Any]:
        """Approve an item, write an audit event, and flush to destinations.

        Args:
            item_id: The item to approve.
            action: Review decision with reviewer and optional reason.

        Returns:
            Dict with ok=True and status=approved.
        """
        self._storage.update_status(item_id, "approved")
        self._storage.write_audit(
            item_id,
            EVENT_APPROVED,
            action.reviewer,
            {"reason": action.reason or ""},
        )

        stored_item = self._storage.get_item(item_id)
        extraction_data: dict[str, Any] = json.loads(stored_item["extraction_json"])  # type: ignore[index]

        destination_row = _build_destination_row(extraction_data)
        await self._flush_to_destinations(item_id, destination_row, reviewer=action.reviewer)

        logger.info(
            "Item approved by reviewer",
            extra={"item_id": item_id, "reviewer": action.reviewer},
        )
        return {"ok": True, "status": "approved"}

    async def _flush_to_destinations(
        self, item_id: str, row: dict[str, Any], *, reviewer: str
    ) -> None:
        """Write an approved row to CRM destinations and send a Slack notification.

        Args:
            item_id: The approved item ID (for audit logging).
            row: Flattened destination row dict.
            reviewer: Reviewer name for the Slack summary.
        """
        append_sheet_row(self._settings.sheets_csv_path, row)
        append_airtable_row(self._settings.airtable_jsonl_path, row)
        self._storage.write_audit(item_id, EVENT_DESTINATIONS_WRITTEN, ACTOR_SYSTEM, {"row": row})

        summary = (
            f"Human-approved intake (reviewer: {reviewer})\n"
            f"- type: {row['request_type']}\n"
            f"- priority: {row['priority']}\n"
            f"- due: {row['due_date'] or 'n/a'}\n"
            f"- company: {row['company'] or 'n/a'}\n"
            f"- requester: {row['requester_name']} <{row['requester_email']}>\n"
            f"- confidence: {row['confidence']}\n"
            f"- item_id: {item_id}"
        )
        await send_slack_summary(self._settings.slack_webhook_url, summary)
        self._storage.write_audit(
            item_id,
            EVENT_SLACK_NOTIFIED,
            ACTOR_SYSTEM,
            {"summary": redact_pii(summary)},
        )


def _build_destination_row(extraction_data: dict[str, Any]) -> dict[str, Any]:
    """Build a flat destination row from a stored extraction dict.

    Args:
        extraction_data: Deserialized extraction JSON from storage.

    Returns:
        Flat dict suitable for CSV/JSONL destination writers.
    """
    requester = extraction_data.get("requester") or {}
    return {
        "request_id": extraction_data.get("request_id", ""),
        "request_type": extraction_data.get("request_type", ""),
        "priority": extraction_data.get("priority", ""),
        "due_date": extraction_data.get("due_date") or "",
        "company": extraction_data.get("company") or "",
        "requester_name": requester.get("name", "") if isinstance(requester, dict) else "",
        "requester_email": requester.get("email", "") if isinstance(requester, dict) else "",
        "confidence": extraction_data.get("confidence", 0.0),
    }
