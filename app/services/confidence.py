"""Confidence scoring.

Pure function — no I/O, no side effects. Takes a validated Extraction
and returns a float in [0.0, 1.0] representing extraction quality.

Score composition (max 1.0):
  Request type identified      0.20   (0 if "other")
  Description substance        0.00–0.20
  Requester completeness       0.15
  Company present              0.15
  Due date present             0.10
  High/urgent priority signal  0.05
  Line-item bonus/penalty      −0.10–0.15  (purchase_request only)
  Non-purchase completeness    0.05        (all other types)
"""

from __future__ import annotations

from app.models import Extraction


def compute_confidence(extraction: Extraction) -> float:
    """Return a confidence score in [0.0, 1.0] for the given extraction.

    Higher scores mean the extraction is well-structured and contains
    enough signal for automated routing. Scores below 0.50 indicate
    the input was too vague to process reliably.

    Args:
        extraction: A validated Extraction from the AI pipeline.

    Returns:
        Float in [0.0, 1.0], rounded to two decimal places.
    """
    score = 0.0

    # --- Request type (0.0–0.20) -----------------------------------------
    # "other" means the AI could not classify the request — strong penalty.
    if extraction.request_type != "other":
        score += 0.20

    # --- Description substance (0.0–0.20) -----------------------------------
    desc_len = len(extraction.description.strip())
    if desc_len >= 100:
        score += 0.20
    elif desc_len >= 40:
        score += 0.12
    elif desc_len >= 15:
        score += 0.05
    # < 15 chars: 0 — effectively noise

    # --- Requester completeness (0.0–0.15) ----------------------------------
    # Requester is always populated from the email envelope, but name quality
    # can vary (some senders use empty or generic names).
    has_name = bool(extraction.requester.name.strip())
    has_email = bool(extraction.requester.email)
    if has_name and has_email:
        score += 0.15
    elif has_email:
        score += 0.08

    # --- Optional enrichment fields -----------------------------------------
    if extraction.company:
        score += 0.15

    if extraction.due_date:
        score += 0.10

    if extraction.priority in ("high", "urgent"):
        score += 0.05

    # --- Purchase-request consistency (−0.10–0.15) --------------------------
    if extraction.request_type == "purchase_request":
        if extraction.line_items:
            score += 0.15
        else:
            score -= 0.10  # purchase request without items is low-signal
    else:
        # Non-purchase types are complete without line items
        score += 0.05

    return round(min(1.0, max(0.0, score)), 2)
