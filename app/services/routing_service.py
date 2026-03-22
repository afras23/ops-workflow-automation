"""Routing service.

Pure function — maps a confidence score to one of three actions:
  auto_approve   confidence > AUTO_APPROVE_THRESHOLD  (default 0.85)
  human_review   confidence ≥ AUTO_REJECT_THRESHOLD   (default 0.50)
  auto_reject    confidence < AUTO_REJECT_THRESHOLD
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.constants import DEFAULT_AUTO_APPROVE_THRESHOLD, DEFAULT_AUTO_REJECT_THRESHOLD

RoutingAction = Literal["auto_approve", "human_review", "auto_reject"]


@dataclass(frozen=True)
class RoutingDecision:
    """The outcome of routing a single item."""

    action: RoutingAction
    confidence: float
    reason: str


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
        auto_reject_threshold: Confidence below this → auto_reject.

    Returns:
        RoutingDecision with action, the input confidence, and a reason string.
    """
    if confidence > auto_approve_threshold:
        return RoutingDecision(
            action="auto_approve",
            confidence=confidence,
            reason=f"confidence {confidence} > auto_approve threshold {auto_approve_threshold}",
        )
    if confidence >= auto_reject_threshold:
        return RoutingDecision(
            action="human_review",
            confidence=confidence,
            reason=(
                f"confidence {confidence} in review band "
                f"[{auto_reject_threshold}, {auto_approve_threshold}]"
            ),
        )
    return RoutingDecision(
        action="auto_reject",
        confidence=confidence,
        reason=f"confidence {confidence} < auto_reject threshold {auto_reject_threshold}",
    )
