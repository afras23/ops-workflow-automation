"""Routing service.

Maps a confidence score to one of three actions:
  auto_approve   confidence > AUTO_APPROVE_THRESHOLD  (default 0.85)
  human_review   confidence ≥ AUTO_REJECT_THRESHOLD   (default 0.50)
  auto_reject    confidence < AUTO_REJECT_THRESHOLD

Every routing decision is logged with correlation_id for auditability.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.constants import DEFAULT_AUTO_APPROVE_THRESHOLD, DEFAULT_AUTO_REJECT_THRESHOLD
from app.core.logging_config import correlation_id_ctx

logger = logging.getLogger(__name__)

RoutingAction = Literal["auto_approve", "human_review", "auto_reject"]


class RoutingDecision(BaseModel):
    """The outcome of routing a single intake item.

    Immutable value object — produced by route() and consumed by WorkflowService.
    """

    model_config = {"frozen": True}

    action: RoutingAction = Field(
        description="Routing action: auto_approve, human_review, or auto_reject"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Extraction confidence score that drove this decision",
    )
    reason: str = Field(
        description="Human-readable explanation of the routing decision for audit logs"
    )


def route(
    confidence: float,
    *,
    auto_approve_threshold: float = DEFAULT_AUTO_APPROVE_THRESHOLD,
    auto_reject_threshold: float = DEFAULT_AUTO_REJECT_THRESHOLD,
) -> RoutingDecision:
    """Determine the routing action for a given confidence score.

    Args:
        confidence: Extraction confidence in [0.0, 1.0].
        auto_approve_threshold: Confidence strictly above this → auto_approve.
        auto_reject_threshold: Confidence at or above this → human_review (else auto_reject).

    Returns:
        RoutingDecision with action, confidence, and reason string.
    """
    if confidence > auto_approve_threshold:
        decision = RoutingDecision(
            action="auto_approve",
            confidence=confidence,
            reason=(f"confidence {confidence} > auto_approve threshold {auto_approve_threshold}"),
        )
    elif confidence >= auto_reject_threshold:
        decision = RoutingDecision(
            action="human_review",
            confidence=confidence,
            reason=(
                f"confidence {confidence} in review band "
                f"[{auto_reject_threshold}, {auto_approve_threshold}]"
            ),
        )
    else:
        decision = RoutingDecision(
            action="auto_reject",
            confidence=confidence,
            reason=(f"confidence {confidence} < auto_reject threshold {auto_reject_threshold}"),
        )

    logger.info(
        "Routing decision made",
        extra={
            "action": decision.action,
            "confidence": confidence,
            "auto_approve_threshold": auto_approve_threshold,
            "auto_reject_threshold": auto_reject_threshold,
            "correlation_id": correlation_id_ctx.get(""),
        },
    )
    return decision
