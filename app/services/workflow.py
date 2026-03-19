"""Workflow service.

Orchestrates the full ops intake pipeline per message:
  ExtractionService → confidence (embedded in Extraction) → route()
  → storage → audit log → destinations (Sheet/CRM/Slack)

Three routing outcomes:
  auto_approve   — confidence > 0.85: written to destinations immediately
  human_review   — 0.50–0.85: queued for human decision
  auto_reject    — confidence < 0.50: logged and discarded

Routes stay thin. All business logic lives here.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.config import Settings
from app.integrations import append_airtable_row, append_sheet_row, send_slack_summary
from app.models import Extraction, InboxMessage, IngestResponse, ReviewAction
from app.prompts.email_extraction import VERSION as PROMPT_VERSION
from app.services.extraction import ExtractionError, ExtractionService
from app.services.routing import RoutingDecision, route
from app.storage import Storage
from app.utils import redact_pii, stable_id

logger = logging.getLogger(__name__)


class WorkflowService:
    """Orchestrates the ops intake pipeline."""

    def __init__(
        self,
        storage: Storage,
        settings: Settings,
        extraction_service: ExtractionService,
    ) -> None:
        self._storage = storage
        self._settings = settings
        self._extraction = extraction_service

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def ingest(self, message: InboxMessage) -> IngestResponse:
        """Process an inbound message through the full pipeline.

        Idempotent: re-submitting the same message_id returns the cached result.

        Args:
            message: Validated inbox message.

        Returns:
            IngestResponse with item_id, status, confidence, and routing outcome.

        Raises:
            ExtractionError: Propagated from ExtractionService for the caller to map to HTTP 400.
        """
        existing = self._storage.get_by_message_id(message.message_id)
        if existing:
            logger.info(
                "Duplicate message_id — returning cached result",
                extra={"message_id": message.message_id, "item_id": existing["item_id"]},
            )
            return IngestResponse(
                item_id=existing["item_id"],
                status=existing["status"],
                confidence=float(existing["confidence"]),
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
                "ingest_failed",
                "system",
                {"error": str(exc), "input_hash": input_hash},
            )
            logger.warning(
                "Ingest failed — extraction error",
                extra={"item_id": item_id, "error": str(exc)},
            )
            raise

        decision = route(
            extraction.confidence,
            auto_approve_threshold=self._settings.auto_approve_threshold,
            auto_reject_threshold=self._settings.auto_reject_threshold,
        )
        status = _decision_to_status(decision)

        self._storage.create_item(
            item_id=item_id,
            message_id=message.message_id,
            status=status,
            confidence=extraction.confidence,
            extraction=extraction.model_dump(),
        )
        self._storage.write_audit(
            item_id,
            "ingested",
            "system",
            {
                "status": status,
                "confidence": extraction.confidence,
                "routing_action": decision.action,
                "routing_reason": decision.reason,
                "input_hash": input_hash,
                "prompt_version": PROMPT_VERSION,
            },
        )

        if decision.action == "auto_approve":
            await self._write_to_destinations(item_id, extraction, actor="system")
        elif decision.action == "auto_reject":
            logger.info(
                "Item auto-rejected",
                extra={"item_id": item_id, "confidence": extraction.confidence, "reason": decision.reason},
            )

        logger.info(
            "Ingest complete",
            extra={
                "item_id": item_id,
                "status": status,
                "confidence": extraction.confidence,
                "routing_action": decision.action,
            },
        )
        return IngestResponse(
            item_id=item_id,
            status=status,
            confidence=extraction.confidence,
            routed_to=decision.action,
        )

    async def handle_review(self, item_id: str, action: ReviewAction) -> dict[str, Any]:
        """Apply a human review decision (approve or reject).

        Args:
            item_id: ID of the pending_review item.
            action: Decision with reviewer name and optional reason.

        Returns:
            Dict with ok=True and resulting status.
        """
        if action.action == "reject":
            self._storage.update_status(item_id, "rejected")
            self._storage.write_audit(item_id, "rejected", action.reviewer, {"reason": action.reason or ""})
            logger.info("Item rejected by reviewer", extra={"item_id": item_id, "reviewer": action.reviewer})
            return {"ok": True, "status": "rejected"}

        self._storage.update_status(item_id, "approved")
        self._storage.write_audit(item_id, "approved", action.reviewer, {"reason": action.reason or ""})

        item = self._storage.get_item(item_id)
        extraction_data: dict[str, Any] = json.loads(item["extraction_json"])  # type: ignore[index]
        await self._write_to_destinations_from_dict(item_id, extraction_data, actor=action.reviewer)

        logger.info("Item approved by reviewer", extra={"item_id": item_id, "reviewer": action.reviewer})
        return {"ok": True, "status": "approved"}

    def list_items(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return a summary list of items, optionally filtered by status."""
        rows = self._storage.list_items(status=status)
        result = []
        for row in rows:
            extraction = json.loads(row["extraction_json"])
            result.append(
                {
                    "item_id": row["item_id"],
                    "message_id": row["message_id"],
                    "status": row["status"],
                    "confidence": row["confidence"],
                    "request_type": extraction.get("request_type") if isinstance(extraction, dict) else None,
                    "priority": extraction.get("priority") if isinstance(extraction, dict) else None,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        """Return full detail for a single item, or None if not found."""
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
        """Return the ordered audit trail for an item."""
        logs = self._storage.list_audit(item_id)
        for entry in logs:
            entry["details"] = json.loads(entry.pop("details_json"))
        return logs

    def item_counts(self) -> dict[str, int]:
        """Return status-keyed item counts for the /metrics endpoint."""
        rows = self._storage.list_items()
        counts: dict[str, int] = {
            "total": len(rows),
            "approved": 0,
            "pending_review": 0,
            "rejected": 0,
            "failed": 0,
        }
        for row in rows:
            s = row["status"]
            if s in counts:
                counts[s] += 1
        return counts

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_to_destinations(self, item_id: str, extraction: Extraction, *, actor: str) -> None:
        row = {
            "request_id": extraction.request_id,
            "request_type": extraction.request_type,
            "priority": extraction.priority,
            "due_date": extraction.due_date or "",
            "company": extraction.company or "",
            "requester_name": extraction.requester.name,
            "requester_email": str(extraction.requester.email),
            "confidence": extraction.confidence,
        }
        await self._flush_row(item_id, row, actor=actor)

    async def _write_to_destinations_from_dict(
        self, item_id: str, data: dict[str, Any], *, actor: str
    ) -> None:
        row = {
            "request_id": data.get("request_id", ""),
            "request_type": data.get("request_type", ""),
            "priority": data.get("priority", ""),
            "due_date": data.get("due_date") or "",
            "company": data.get("company") or "",
            "requester_name": data.get("requester", {}).get("name", ""),
            "requester_email": data.get("requester", {}).get("email", ""),
            "confidence": data.get("confidence", 0.0),
        }
        await self._flush_row(item_id, row, actor=actor)

    async def _flush_row(self, item_id: str, row: dict[str, Any], *, actor: str) -> None:
        append_sheet_row(self._settings.sheets_csv_path, row)
        append_airtable_row(self._settings.airtable_jsonl_path, row)
        self._storage.write_audit(item_id, "destinations_written", "system", {"row": row})

        label = "Auto-approved" if actor == "system" else f"Human-approved (reviewer: {actor})"
        summary = (
            f"{label} intake\n"
            f"- type: {row['request_type']}\n"
            f"- priority: {row['priority']}\n"
            f"- due: {row['due_date'] or 'n/a'}\n"
            f"- company: {row['company'] or 'n/a'}\n"
            f"- requester: {row['requester_name']} <{row['requester_email']}>\n"
            f"- confidence: {row['confidence']}\n"
            f"- item_id: {item_id}"
        )
        await send_slack_summary(self._settings.slack_webhook_url, summary)
        self._storage.write_audit(item_id, "slack_notified", "system", {"summary": redact_pii(summary)})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision_to_status(decision: RoutingDecision) -> str:
    mapping = {
        "auto_approve": "approved",
        "human_review": "pending_review",
        "auto_reject": "rejected",
    }
    return mapping[decision.action]


def _hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
