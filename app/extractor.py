from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from dateutil.parser import parse as dt_parse
from jsonschema import Draft202012Validator

from app.models import Extraction, InboxMessage, Requester, LineItem
from app.utils import stable_id, normalize_whitespace

PRIORITY_HINTS = {
    "urgent": "urgent",
    "asap": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

TYPE_HINTS = [
    ("purchase", "purchase_request"),
    ("order", "purchase_request"),
    ("billing", "customer_issue"),
    ("error", "customer_issue"),
    ("issue", "customer_issue"),
    ("incident", "customer_issue"),
    ("change request", "ops_change"),
    ("change", "ops_change"),
    ("update", "ops_change"),
]

COMPANY_RE = re.compile(r"\bCompany:\s*(.+)\b", re.IGNORECASE)
PRIORITY_RE = re.compile(r"\bPriority:\s*(urgent|high|medium|low)\b", re.IGNORECASE)
DUE_RE = re.compile(r"\b(N(?:eeded)? by|Due|Deadline):?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Za-z]{3,9}\s+\d{1,2})\b", re.IGNORECASE)
LINE_ITEM_RE = re.compile(r"\bItem:\s*(.+?),\s*Qty:\s*(\d+)\b", re.IGNORECASE)

def load_schema_validator(schema_path: str) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)

def detect_request_type(subject: str, body: str) -> tuple[str, list[str]]:
    text = (subject + " " + body).lower()
    notes: list[str] = []
    for key, mapped in TYPE_HINTS:
        if key in text:
            notes.append(f"type_hint:{key}->{mapped}")
            return mapped, notes
    return "other", ["type_hint:none"]

def detect_priority(subject: str, body: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    m = PRIORITY_RE.search(body)
    if m:
        p = m.group(1).lower()
        notes.append("priority_explicit:body")
        return p, notes

    text = (subject + " " + body).lower()
    for hint, p in PRIORITY_HINTS.items():
        if hint in text:
            notes.append(f"priority_hint:{hint}")
            return p, notes

    return "medium", ["priority_default:medium"]

def detect_company(body: str) -> tuple[str | None, list[str]]:
    m = COMPANY_RE.search(body)
    if m:
        return normalize_whitespace(m.group(1)), ["company_explicit"]
    return None, ["company:none"]

def detect_due_date(subject: str, body: str) -> tuple[str | None, list[str]]:
    text = subject + "\n" + body
    m = DUE_RE.search(text)
    if not m:
        return None, ["due:none"]
    raw = m.group(2).strip()
    try:
        dt = dt_parse(raw, dayfirst=False, fuzzy=True)
        return dt.date().isoformat(), [f"due_parsed:{raw}"]
    except Exception:
        return None, [f"due_parse_failed:{raw}"]

def detect_line_items(body: str) -> tuple[list[LineItem], list[str]]:
    notes: list[str] = []
    items: list[LineItem] = []
    for m in LINE_ITEM_RE.finditer(body):
        item = normalize_whitespace(m.group(1))
        qty = int(m.group(2))
        items.append(LineItem(item=item, qty=qty))
    if items:
        notes.append(f"line_items:{len(items)}")
    else:
        notes.append("line_items:none")
    return items, notes

def compute_confidence(
    request_type: str,
    priority: str,
    company: str | None,
    due_date: str | None,
    description: str,
    line_items_count: int,
    notes: list[str],
) -> float:
    score = 0.4  # base

    if request_type != "other":
        score += 0.15
    if priority in ("high", "urgent"):
        score += 0.05
    if company:
        score += 0.10
    if due_date:
        score += 0.10
    if len(description) >= 30:
        score += 0.10
    if line_items_count > 0:
        score += 0.10

    # Penalize low-signal extraction
    if "type_hint:none" in notes:
        score -= 0.08
    if "line_items:none" in notes and request_type == "purchase_request":
        score -= 0.10

    return max(0.0, min(1.0, round(score, 2)))

def extract(message: InboxMessage, schema_validator: Draft202012Validator) -> Extraction:
    subject = message.subject
    body = message.body

    request_type, type_notes = detect_request_type(subject, body)
    priority, priority_notes = detect_priority(subject, body)
    company, company_notes = detect_company(body)
    due_date, due_notes = detect_due_date(subject, body)
    line_items, li_notes = detect_line_items(body)

    description = normalize_whitespace(body)
    request_id = stable_id(message.message_id, message.from_.email, subject)

    requester = Requester(name=message.from_.name, email=message.from_.email)

    notes = []
    notes.extend(type_notes)
    notes.extend(priority_notes)
    notes.extend(company_notes)
    notes.extend(due_notes)
    notes.extend(li_notes)

    confidence = compute_confidence(
        request_type=request_type,
        priority=priority,
        company=company,
        due_date=due_date,
        description=description,
        line_items_count=len(line_items),
        notes=notes,
    )

    extraction = Extraction(
        request_id=request_id,
        request_type=request_type,   # type: ignore[arg-type]
        priority=priority,           # type: ignore[arg-type]
        due_date=due_date,
        company=company,
        requester=requester,
        description=description,
        line_items=line_items,
        confidence=confidence,
        extraction_notes=notes,
    )

    # Guardrail: validate against JSON schema (separate from Pydantic)
    payload = extraction.model_dump()
    errors = sorted(schema_validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        msg = "; ".join([f"{list(e.path)}: {e.message}" for e in errors])
        raise ValueError(f"Schema validation failed: {msg}")

    return extraction
