from __future__ import annotations
from app.models import Extraction

def needs_human_review(extraction: Extraction, threshold: float) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if extraction.confidence < threshold:
        reasons.append(f"confidence_below_threshold:{extraction.confidence}<{threshold}")

    # Additional guardrails
    if extraction.request_type == "other":
        reasons.append("unknown_request_type")
    if len(extraction.description) < 25:
        reasons.append("low_signal_description")
    if extraction.request_type == "purchase_request" and not extraction.line_items:
        reasons.append("purchase_missing_line_items")

    return (len(reasons) > 0), reasons
