from __future__ import annotations

import json
import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models import InboxMessage, IngestResponse, ReviewAction
from app.extractor import extract, load_schema_validator
from app.reviewer import needs_human_review
from app.storage import Storage
from app.integrations import send_slack_summary, append_sheet_row, append_airtable_row
from app.utils import stable_id, redact_pii

app = FastAPI(title="Ops Workflow Automation", version="1.0.0")

settings = get_settings()
storage = Storage(settings.sqlite_path)
schema_validator = load_schema_validator("schemas/extraction_schema.json")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/ingest", response_model=IngestResponse)
async def ingest(message: InboxMessage):
    # Idempotency: do not reprocess the same message_id
    existing = storage.get_by_message_id(message.message_id)
    if existing:
        extraction = json.loads(existing["extraction_json"])
        return IngestResponse(
            item_id=existing["item_id"],
            status=existing["status"],
            confidence=float(existing["confidence"]),
            routed_to="idempotent_return",
        )

    item_id = stable_id("item", message.message_id)

    try:
        extraction = extract(message, schema_validator)
    except Exception as e:
        storage.create_item(
            item_id=item_id,
            message_id=message.message_id,
            status="failed",
            confidence=0.0,
            extraction={"error": str(e)},
        )
        storage.write_audit(item_id, "ingest_failed", "system", {"error": str(e)})
        raise HTTPException(status_code=400, detail=f"Extraction failed: {str(e)}")

    review_needed, reasons = needs_human_review(extraction, settings.confidence_threshold)
    status = "pending_review" if review_needed else "approved"

    storage.create_item(
        item_id=item_id,
        message_id=message.message_id,
        status=status,
        confidence=extraction.confidence,
        extraction=extraction.model_dump(),
    )

    storage.write_audit(
        item_id,
        "ingested",
        "system",
        {"status": status, "confidence": extraction.confidence, "review_reasons": reasons},
    )

    # If auto-approved, write to "Sheet/CRM" mocks and send Slack summary
    if status == "approved":
        row = {
            "request_id": extraction.request_id,
            "request_type": extraction.request_type,
            "priority": extraction.priority,
            "due_date": extraction.due_date or "",
            "company": extraction.company or "",
            "requester_name": extraction.requester.name,
            "requester_email": extraction.requester.email,
            "confidence": extraction.confidence,
        }
        append_sheet_row(settings.sheets_csv_path, row)
        append_airtable_row(settings.airtable_jsonl_path, row)
        storage.write_audit(item_id, "destinations_written", "system", {"row": row})

        summary = (
            f"Auto-approved intake\n"
            f"- type: {extraction.request_type}\n"
            f"- priority: {extraction.priority}\n"
            f"- due: {extraction.due_date or 'n/a'}\n"
            f"- company: {extraction.company or 'n/a'}\n"
            f"- requester: {extraction.requester.name} <{extraction.requester.email}>\n"
            f"- confidence: {extraction.confidence}\n"
            f"- item_id: {item_id}"
        )
        await send_slack_summary(settings.slack_webhook_url, summary)
        storage.write_audit(item_id, "slack_notified", "system", {"summary": redact_pii(summary)})

    routed_to = "human_review_queue" if status == "pending_review" else "auto_approved"
    return IngestResponse(item_id=item_id, status=status, confidence=extraction.confidence, routed_to=routed_to)

@app.get("/items")
def list_items(status: str | None = Query(default=None)):
    items = storage.list_items(status=status)
    # Hide raw extraction_json in list view by default; keep a summary
    out = []
    for it in items:
        extraction = json.loads(it["extraction_json"])
        out.append({
            "item_id": it["item_id"],
            "message_id": it["message_id"],
            "status": it["status"],
            "confidence": it["confidence"],
            "request_type": extraction.get("request_type") if isinstance(extraction, dict) else None,
            "priority": extraction.get("priority") if isinstance(extraction, dict) else None,
            "created_at": it["created_at"],
            "updated_at": it["updated_at"],
        })
    return out

@app.get("/items/{item_id}")
def get_item(item_id: str):
    it = storage.get_item(item_id)
    if not it:
        raise HTTPException(status_code=404, detail="Not found")
    extraction = json.loads(it["extraction_json"])
    return {
        "item_id": it["item_id"],
        "message_id": it["message_id"],
        "status": it["status"],
        "confidence": it["confidence"],
        "extraction": extraction,
        "created_at": it["created_at"],
        "updated_at": it["updated_at"],
    }

@app.get("/items/{item_id}/audit")
def get_audit(item_id: str):
    it = storage.get_item(item_id)
    if not it:
        raise HTTPException(status_code=404, detail="Not found")
    logs = storage.list_audit(item_id)
    # parse details_json
    for l in logs:
        l["details"] = json.loads(l.pop("details_json"))
    return logs

@app.post("/items/{item_id}/review")
async def review_item(item_id: str, action: ReviewAction):
    it = storage.get_item(item_id)
    if not it:
        raise HTTPException(status_code=404, detail="Not found")

    if it["status"] not in ("pending_review",):
        raise HTTPException(status_code=400, detail=f"Item not in pending_review (current={it['status']})")

    extraction = json.loads(it["extraction_json"])

    if action.action == "reject":
        storage.update_status(item_id, "rejected")
        storage.write_audit(item_id, "rejected", action.reviewer, {"reason": action.reason or ""})
        return JSONResponse({"ok": True, "status": "rejected"})

    # Approve path
    storage.update_status(item_id, "approved")
    storage.write_audit(item_id, "approved", action.reviewer, {"reason": action.reason or ""})

    row = {
        "request_id": extraction.get("request_id", ""),
        "request_type": extraction.get("request_type", ""),
        "priority": extraction.get("priority", ""),
        "due_date": extraction.get("due_date") or "",
        "company": extraction.get("company") or "",
        "requester_name": extraction.get("requester", {}).get("name", ""),
        "requester_email": extraction.get("requester", {}).get("email", ""),
        "confidence": extraction.get("confidence", 0.0),
    }
    append_sheet_row(settings.sheets_csv_path, row)
    append_airtable_row(settings.airtable_jsonl_path, row)
    storage.write_audit(item_id, "destinations_written", "system", {"row": row})

    summary = (
        f"Human-approved intake\n"
        f"- type: {row['request_type']}\n"
        f"- priority: {row['priority']}\n"
        f"- due: {row['due_date'] or 'n/a'}\n"
        f"- company: {row['company'] or 'n/a'}\n"
        f"- requester: {row['requester_name']} <{row['requester_email']}>\n"
        f"- confidence: {row['confidence']}\n"
        f"- item_id: {item_id}\n"
        f"- reviewer: {action.reviewer}"
    )
    await send_slack_summary(settings.slack_webhook_url, summary)
    storage.write_audit(item_id, "slack_notified", "system", {"summary": redact_pii(summary)})

    return JSONResponse({"ok": True, "status": "approved"})
