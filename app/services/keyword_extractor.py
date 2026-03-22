"""Keyword-based extraction service (rule-based fallback).

Extracts structured fields from email text using regex patterns and
keyword matching, without calling an AI provider. Used for testing
and as a reference implementation for the confidence scoring inputs.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from dateutil.parser import parse as dt_parse
from jsonschema import Draft202012Validator

from app.models.email import Extraction, InboxMessage, LineItem, Requester
from app.utils import normalize_whitespace, stable_id

logger = logging.getLogger(__name__)

_PRIORITY_HINTS: dict[str, str] = {
    "urgent": "urgent",
    "asap": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

_TYPE_HINTS: list[tuple[str, str]] = [
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

_COMPANY_RE = re.compile(r"\bCompany:\s*(.+)\b", re.IGNORECASE)
_PRIORITY_RE = re.compile(r"\bPriority:\s*(urgent|high|medium|low)\b", re.IGNORECASE)
_DUE_RE = re.compile(
    r"\b(N(?:eeded)? by|Due|Deadline):?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Za-z]{3,9}\s+\d{1,2})\b",
    re.IGNORECASE,
)
_LINE_ITEM_RE = re.compile(r"\bItem:\s*(.+?),\s*Qty:\s*(\d+)\b", re.IGNORECASE)


def load_schema_validator(schema_path: str) -> Draft202012Validator:
    """Load a JSON Schema Draft 2020-12 validator from a file.

    Args:
        schema_path: Path to the JSON schema file.

    Returns:
        Configured Draft202012Validator instance.
    """
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def detect_request_type(subject: str, body: str) -> tuple[str, list[str]]:
    """Detect request type from subject and body text using keyword matching.

    Args:
        subject: Email subject line.
        body: Email body text.

    Returns:
        Tuple of (request_type, extraction_notes).
    """
    text = (subject + " " + body).lower()
    for keyword, mapped_type in _TYPE_HINTS:
        if keyword in text:
            return mapped_type, [f"type_hint:{keyword}->{mapped_type}"]
    return "other", ["type_hint:none"]


def detect_priority(subject: str, body: str) -> tuple[str, list[str]]:
    """Detect priority from explicit markers or keyword hints.

    Args:
        subject: Email subject line.
        body: Email body text.

    Returns:
        Tuple of (priority, extraction_notes).
    """
    priority_match = _PRIORITY_RE.search(body)
    if priority_match:
        detected_priority = priority_match.group(1).lower()
        return detected_priority, ["priority_explicit:body"]

    text = (subject + " " + body).lower()
    for hint, mapped_priority in _PRIORITY_HINTS.items():
        if hint in text:
            return mapped_priority, [f"priority_hint:{hint}"]

    return "medium", ["priority_default:medium"]


def detect_company(body: str) -> tuple[str | None, list[str]]:
    """Extract company name from an explicit 'Company: ...' marker.

    Args:
        body: Email body text.

    Returns:
        Tuple of (company or None, extraction_notes).
    """
    company_match = _COMPANY_RE.search(body)
    if company_match:
        return normalize_whitespace(company_match.group(1)), ["company_explicit"]
    return None, ["company:none"]


def detect_due_date(subject: str, body: str) -> tuple[str | None, list[str]]:
    """Parse a due date from explicit deadline markers.

    Args:
        subject: Email subject line.
        body: Email body text.

    Returns:
        Tuple of (ISO date string or None, extraction_notes).
    """
    due_match = _DUE_RE.search(subject + "\n" + body)
    if not due_match:
        return None, ["due:none"]

    raw_date = due_match.group(2).strip()
    try:
        parsed_date = dt_parse(raw_date, dayfirst=False, fuzzy=True)
        return parsed_date.date().isoformat(), [f"due_parsed:{raw_date}"]
    except ValueError:
        return None, [f"due_parse_failed:{raw_date}"]


def detect_line_items(body: str) -> tuple[list[LineItem], list[str]]:
    """Extract 'Item: ..., Qty: N' line items from purchase request text.

    Args:
        body: Email body text.

    Returns:
        Tuple of (list of LineItem, extraction_notes).
    """
    items: list[LineItem] = []
    for match in _LINE_ITEM_RE.finditer(body):
        item_name = normalize_whitespace(match.group(1))
        item_qty = int(match.group(2))
        items.append(LineItem(item=item_name, qty=item_qty))

    if items:
        return items, [f"line_items:{len(items)}"]
    return items, ["line_items:none"]


def _score_confidence(
    request_type: str,
    priority: str,
    company: str | None,
    due_date: str | None,
    description: str,
    line_items_count: int,
    notes: list[str],
) -> float:
    """Compute a confidence score for keyword-based extraction results.

    Args:
        request_type: Detected request type.
        priority: Detected priority.
        company: Detected company or None.
        due_date: Detected due date or None.
        description: Normalized email body text.
        line_items_count: Number of detected line items.
        notes: Extraction notes list for penalty detection.

    Returns:
        Float in [0.0, 1.0].
    """
    score = 0.4  # base score for keyword extraction

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
    if "type_hint:none" in notes:
        score -= 0.08
    if "line_items:none" in notes and request_type == "purchase_request":
        score -= 0.10

    return max(0.0, min(1.0, round(score, 2)))


def extract(message: InboxMessage, schema_validator: Draft202012Validator) -> Extraction:
    """Extract structured fields from a message using keyword/regex rules.

    Validates the result against a JSON Schema before returning.

    Args:
        message: Validated inbox message to extract from.
        schema_validator: Pre-loaded Draft202012Validator for output validation.

    Returns:
        Extraction with all fields populated and confidence scored.

    Raises:
        ValueError: If the extraction fails JSON Schema validation.
    """
    request_type, type_notes = detect_request_type(message.subject, message.body)
    priority, priority_notes = detect_priority(message.subject, message.body)
    company, company_notes = detect_company(message.body)
    due_date, due_notes = detect_due_date(message.subject, message.body)
    line_items, li_notes = detect_line_items(message.body)

    description = normalize_whitespace(message.body)
    request_id = stable_id(message.message_id, str(message.from_.email), message.subject)
    requester = Requester(name=message.from_.name, email=message.from_.email)

    all_notes: list[str] = type_notes + priority_notes + company_notes + due_notes + li_notes

    confidence_score = _score_confidence(
        request_type=request_type,
        priority=priority,
        company=company,
        due_date=due_date,
        description=description,
        line_items_count=len(line_items),
        notes=all_notes,
    )

    extraction = Extraction(
        request_id=request_id,
        request_type=request_type,  # type: ignore[arg-type]
        priority=priority,  # type: ignore[arg-type]
        due_date=due_date,
        company=company,
        requester=requester,
        description=description,
        line_items=line_items,
        confidence=confidence_score,
        extraction_notes=all_notes,
    )

    payload: dict[str, Any] = extraction.model_dump()
    schema_errors = sorted(schema_validator.iter_errors(payload), key=lambda e: e.path)
    if schema_errors:
        error_summary = "; ".join([f"{list(err.path)}: {err.message}" for err in schema_errors])
        raise ValueError(f"Schema validation failed: {error_summary}")

    return extraction
