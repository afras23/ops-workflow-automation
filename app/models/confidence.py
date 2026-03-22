"""Pydantic model for the confidence scoring result."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfidenceResult(BaseModel):
    """Composite extraction confidence score decomposed into three components.

    Produced by confidence_service.compute_confidence() and consumed by
    ExtractionService to set the confidence field on Extraction.
    """

    score: float = Field(ge=0.0, le=1.0, description="Final weighted confidence score in [0, 1]")
    completeness_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Completeness component (weight 0.4): description, requester, company, due date",
    )
    type_compliance_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Type compliance component (weight 0.4): request_type specificity and field rules",
    )
    ai_confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="AI self-confidence component (weight 0.2): inferred from extraction_notes count",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Scoring observations for audit trail and diagnostics",
    )
