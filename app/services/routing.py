"""Routing logic.

Pure function — maps a confidence score to one of three actions:
  auto_approve   confidence > AUTO_APPROVE_THRESHOLD  (default 0.85)
  human_review   confidence ≥ AUTO_REJECT_THRESHOLD   (default 0.50)
  auto_reject    confidence < AUTO_REJECT_THRESHOLD

Thresholds are configurable so they can be tuned per deployment without
touching code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RoutingAction = Literal["auto_approve", "human_review", "auto_reject"]

# Default thresholds — overridden by Settings in production
DEFAULT_AUTO_APPROVE = 0.85
DEFAULT_AUTO_REJECT = 0.50


@dataclass(frozen=True)
class RoutingDecision:
    """The outcome of routing a single item."""

    action: RoutingAction
    confidence: float
    reason: str


def route(
    confidence: float,
    *,
    auto_approve_threshold: float = DEFAULT_AUTO_APPROVE,
    auto_reject_threshold: float = DEFAULT_AUTO_REJECT,
) -> RoutingDecision:
    """Determine the routing action for a given confidence score.

    Args:
        confidence: Extraction confidence in [0.0, 1.0].
        auto_approve_threshold: Confidence above which items are auto-approved.
        auto_reject_threshold: Confidence below which items are auto-rejected.

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
            reason=f"confidence {confidence} in review band [{auto_reject_threshold}, {auto_approve_threshold}]",
        )
    return RoutingDecision(
        action="auto_reject",
        confidence=confidence,
        reason=f"confidence {confidence} < auto_reject threshold {auto_reject_threshold}",
    )
