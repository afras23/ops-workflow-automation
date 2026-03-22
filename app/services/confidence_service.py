"""Confidence scoring service.

Composite score: completeness (0.4) + type_compliance (0.4) + ai_confidence (0.2).
Each component is normalised to [0.0, 1.0]; weights sum to 1.0.

Components:
  completeness    — description substance, requester identity, company, due date
  type_compliance — request_type specificity and required-field rules per type
  ai_confidence   — inferred from extraction_notes count (fewer = more confident)
"""

from __future__ import annotations

from app.models.confidence import ConfidenceResult
from app.models.email import Extraction

_COMPLETENESS_WEIGHT: float = 0.4
_TYPE_COMPLIANCE_WEIGHT: float = 0.4
_AI_CONFIDENCE_WEIGHT: float = 0.2


def compute_confidence(extraction: Extraction) -> ConfidenceResult:
    """Return a ConfidenceResult for the given extraction.

    Args:
        extraction: Validated Extraction from the AI pipeline.

    Returns:
        ConfidenceResult with per-component scores and a weighted final score.
    """
    completeness, completeness_notes = _score_completeness(extraction)
    type_compliance, type_notes = _score_type_compliance(extraction)
    ai_confidence, ai_notes = _score_ai_confidence(extraction)

    raw_score = (
        completeness * _COMPLETENESS_WEIGHT
        + type_compliance * _TYPE_COMPLIANCE_WEIGHT
        + ai_confidence * _AI_CONFIDENCE_WEIGHT
    )

    return ConfidenceResult(
        score=round(min(1.0, max(0.0, raw_score)), 2),
        completeness_score=completeness,
        type_compliance_score=type_compliance,
        ai_confidence_score=ai_confidence,
        notes=completeness_notes + type_notes + ai_notes,
    )


def _score_completeness(extraction: Extraction) -> tuple[float, list[str]]:
    """Score data completeness on a [0.0, 1.0] scale.

    Rubric (max 1.0):
      description ≥100 chars: 0.40 | 40–99: 0.28 | 15–39: 0.12 | <15: 0.0
      requester name+email:   0.30 | email only: 0.15 | neither: 0.0
      company present:        0.20
      due_date present:       0.10

    Args:
        extraction: Validated extraction to score.

    Returns:
        Tuple of (score in [0.0, 1.0], list of scoring notes).
    """
    score = 0.0
    notes: list[str] = []

    desc_len = len(extraction.description.strip())
    if desc_len >= 100:
        score += 0.40
    elif desc_len >= 40:
        score += 0.28
    elif desc_len >= 15:
        score += 0.12
    else:
        notes.append("description too short to contribute to score")

    has_name = bool(extraction.requester.name.strip())
    has_email = bool(extraction.requester.email)
    if has_name and has_email:
        score += 0.30
    elif has_email:
        score += 0.15
        notes.append("requester name missing")
    else:
        notes.append("requester identity incomplete")

    if extraction.company:
        score += 0.20
    else:
        notes.append("company not identified")

    if extraction.due_date:
        score += 0.10
    else:
        notes.append("no due date specified")

    return round(min(1.0, score), 4), notes


def _score_type_compliance(extraction: Extraction) -> tuple[float, list[str]]:
    """Score type-specific rule compliance on a [0.0, 1.0] scale.

    Rules:
      "other"                         → 0.0   (unclassified)
      purchase_request + line_items   → 1.0
      purchase_request − line_items   → 0.30  (penalised)
      all other named types           → 1.0   (no extra required fields)

    Args:
        extraction: Validated extraction to score.

    Returns:
        Tuple of (score in [0.0, 1.0], list of scoring notes).
    """
    if extraction.request_type == "other":
        return 0.0, ["request type could not be classified"]

    if extraction.request_type == "purchase_request":
        if extraction.line_items:
            return 1.0, []
        return 0.30, ["purchase_request has no line items"]

    return 1.0, []


def _score_ai_confidence(extraction: Extraction) -> tuple[float, list[str]]:
    """Infer AI self-confidence from extraction_notes count.

    Fewer notes signals the AI encountered fewer ambiguities.
    Scale: 0 notes → 0.8, 1 → 0.6, 2 → 0.4, 3+ → 0.2.

    Args:
        extraction: Validated extraction to score.

    Returns:
        Tuple of (score in [0.0, 1.0], list of scoring notes).
    """
    note_count = len(extraction.extraction_notes)
    if note_count == 0:
        return 0.8, []
    if note_count == 1:
        return 0.6, []
    if note_count == 2:
        return 0.4, []
    return 0.2, [f"AI flagged {note_count} extraction ambiguities"]
