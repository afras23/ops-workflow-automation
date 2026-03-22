"""Workflow service — orchestrates the full ops intake pipeline per message.

Pipeline: ExtractionService → confidence score → route()
  → persist item → write audit → dispatch to destinations (if auto_approve)

Idempotent: re-submitting the same message_id returns the cached result.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.config import Settings
from app.core.constants import (
    ACTOR_SYSTEM,
    EVENT_DESTINATIONS_WRITTEN,
    EVENT_INGEST_FAILED,
    EVENT_INGESTED,
    EVENT_SLACK_NOTIFIED,
)
from app.core.exceptions import ExtractionError
from app.integrations.crm_client import append_airtable_row, append_sheet_row
from app.integrations.slack_client import send_slack_summary
from app.models.email import Extraction, InboxMessage, IngestResponse, Status
from app.services.ai.prompts import VERSION as PROMPT_VERSION
from app.services.extraction_service import ExtractionService
from app.services.routing_service import RoutingDecision, route
from app.storage import Storage
from app.utils import redact_pii, stable_id

logger = logging.getLogger(__name__)


class WorkflowService:
    """Orchestrates the ops intake pipeline from message ingestion to routing."""

    def __init__(
        self,
        storage: Storage,
        settings: Settings,
        extraction_service: ExtractionService,
    ) -> None:
        """Initialise with storage, settings, and the extraction service.

        Args:
            storage: SQLite storage backend.
            settings: Application configuration (thresholds, destinations).
            extraction_service: AI pipeline for field extraction.
        """
        self._storage = storage
        self._settings = settings
        self._extraction = extraction_service

    async def ingest(self, message: InboxMessage) -> IngestResponse:
        """Process an inbound message through the full pipeline.

        Idempotent: re-submitting the same message_id returns the cached result.

        Args:
            message: Validated inbox message.

        Returns:
            IngestResponse with item_id, status, confidence, and routing outcome.

        Raises:
            ExtractionError: Propagated from ExtractionService (map to HTTP 422).
        """
        existing_item = self._storage.get_by_message_id(message.message_id)
        if existing_item:
            logger.info(
                "Duplicate message_id — returning cached result",
                extra={
                    "message_id": message.message_id,
                    "item_id": existing_item["item_id"],
                },
            )
            return IngestResponse(
                item_id=existing_item["item_id"],
                status=existing_item["status"],
                confidence=float(existing_item["confidence"]),
                routed_to="idempotent_return",
            )

        item_id = stable_id("item", message.message_id)
        input_hash = _hash_body(message.body)

        try:
            extraction = await self._extraction.extract(message)
        except ExtractionError as exc:
            self._storage.create_item(
                item_id=item_id,
                message_id=message.message_id,
                status="failed",
                confidence=0.0,
                extraction={"error": str(exc)},
            )
            self._storage.write_audit(
                item_id,
                EVENT_INGEST_FAILED,
                ACTOR_SYSTEM,
                {"error": str(exc), "input_hash": input_hash},
            )
            logger.warning(
                "Ingest failed — extraction error",
                extra={"item_id": item_id, "error": str(exc)},
            )
            raise

        routing_decision = route(
            extraction.confidence,
            auto_approve_threshold=self._settings.auto_approve_threshold,
            auto_reject_threshold=self._settings.auto_reject_threshold,
        )
        item_status = _decision_to_status(routing_decision)

        self._storage.create_item(
            item_id=item_id,
            message_id=message.message_id,
            status=item_status,
            confidence=extraction.confidence,
            extraction=extraction.model_dump(),
        )
        self._storage.write_audit(
            item_id,
            EVENT_INGESTED,
            ACTOR_SYSTEM,
            {
                "status": item_status,
                "confidence": extraction.confidence,
                "routing_action": routing_decision.action,
                "routing_reason": routing_decision.reason,
                "input_hash": input_hash,
                "prompt_version": PROMPT_VERSION,
            },
        )

        if routing_decision.action == "auto_approve":
            await self._write_to_destinations(item_id, extraction)
        elif routing_decision.action == "auto_reject":
            logger.info(
                "Item auto-rejected",
                extra={
                    "item_id": item_id,
                    "confidence": extraction.confidence,
                    "reason": routing_decision.reason,
                },
            )

        logger.info(
            "Ingest complete",
            extra={
                "item_id": item_id,
                "status": item_status,
                "confidence": extraction.confidence,
                "routing_action": routing_decision.action,
            },
        )
        return IngestResponse(
            item_id=item_id,
            status=item_status,
            confidence=extraction.confidence,
            routed_to=routing_decision.action,
        )

    def list_items(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return a summary list of items, optionally filtered by status.

        Args:
            status: Optional status filter.

        Returns:
            List of item summary dicts ordered by created_at descending.
        """
        import json

        rows = self._storage.list_items(status=status)
        item_summaries = []
        for row in rows:
            extraction = json.loads(row["extraction_json"])
            item_summaries.append(
                {
                    "item_id": row["item_id"],
                    "message_id": row["message_id"],
                    "status": row["status"],
                    "confidence": row["confidence"],
                    "request_type": extraction.get("request_type")
                    if isinstance(extraction, dict)
                    else None,
                    "priority": extraction.get("priority")
                    if isinstance(extraction, dict)
                    else None,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return item_summaries

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        """Return full detail for a single item, or None if not found.

        Args:
            item_id: Stable item identifier.

        Returns:
            Item detail dict, or None if not found.
        """
        import json

        row = self._storage.get_item(item_id)
        if not row:
            return None
        return {
            "item_id": row["item_id"],
            "message_id": row["message_id"],
            "status": row["status"],
            "confidence": row["confidence"],
            "extraction": json.loads(row["extraction_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_audit(self, item_id: str) -> list[dict[str, Any]]:
        """Return the ordered audit trail for an item.

        Args:
            item_id: The item whose audit log to retrieve.

        Returns:
            List of audit entry dicts in chronological order.
        """
        import json

        audit_logs = self._storage.list_audit(item_id)
        for entry in audit_logs:
            entry["details"] = json.loads(entry.pop("details_json"))
        return audit_logs

    def item_counts(self) -> dict[str, int]:
        """Return status-keyed item counts for the /metrics endpoint.

        Returns:
            Dict of status → count, plus a "total" key.
        """
        rows = self._storage.list_items()
        status_counts: dict[str, int] = {
            "total": len(rows),
            "approved": 0,
            "pending_review": 0,
            "rejected": 0,
            "failed": 0,
        }
        for row in rows:
            item_status = row["status"]
            if item_status in status_counts:
                status_counts[item_status] += 1
        return status_counts

    async def _write_to_destinations(self, item_id: str, extraction: Extraction) -> None:
        """Write an auto-approved item to CRM destinations and send a Slack alert.

        Args:
            item_id: The approved item ID (for audit logging).
            extraction: The extraction model to serialize for destinations.
        """
        destination_row = {
            "request_id": extraction.request_id,
            "request_type": extraction.request_type,
            "priority": extraction.priority,
            "due_date": extraction.due_date or "",
            "company": extraction.company or "",
            "requester_name": extraction.requester.name,
            "requester_email": str(extraction.requester.email),
            "confidence": extraction.confidence,
        }

        append_sheet_row(self._settings.sheets_csv_path, destination_row)
        append_airtable_row(self._settings.airtable_jsonl_path, destination_row)
        self._storage.write_audit(
            item_id, EVENT_DESTINATIONS_WRITTEN, ACTOR_SYSTEM, {"row": destination_row}
        )

        slack_summary = (
            f"Auto-approved intake\n"
            f"- type: {destination_row['request_type']}\n"
            f"- priority: {destination_row['priority']}\n"
            f"- due: {destination_row['due_date'] or 'n/a'}\n"
            f"- company: {destination_row['company'] or 'n/a'}\n"
            f"- requester: {destination_row['requester_name']} <{destination_row['requester_email']}>\n"
            f"- confidence: {destination_row['confidence']}\n"
            f"- item_id: {item_id}"
        )
        await send_slack_summary(self._settings.slack_webhook_url, slack_summary)
        self._storage.write_audit(
            item_id,
            EVENT_SLACK_NOTIFIED,
            ACTOR_SYSTEM,
            {"summary": redact_pii(slack_summary)},
        )


def _decision_to_status(decision: RoutingDecision) -> Status:
    """Map a routing action to a storage status string.

    Args:
        decision: The routing decision from route().

    Returns:
        Storage status string.
    """
    action_to_status: dict[str, Status] = {
        "auto_approve": "approved",
        "human_review": "pending_review",
        "auto_reject": "rejected",
    }
    return action_to_status[decision.action]


def _hash_body(body: str) -> str:
    """Return a short SHA-256 hex digest of the email body.

    Args:
        body: Raw email body text.

    Returns:
        16-character lowercase hex string.
    """
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
