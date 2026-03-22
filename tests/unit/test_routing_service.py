"""Tests for the routing service.

route() is a pure function — no mocks, no I/O.
"""

from __future__ import annotations

import pytest

from app.services.routing_service import RoutingDecision, route

# ---------------------------------------------------------------------------
# Core three-way routing
# ---------------------------------------------------------------------------


def test_high_confidence_auto_approves() -> None:
    routing_decision = route(0.90)
    assert routing_decision.action == "auto_approve"


def test_mid_confidence_goes_to_review() -> None:
    routing_decision = route(0.70)
    assert routing_decision.action == "human_review"


def test_low_confidence_auto_rejects() -> None:
    routing_decision = route(0.30)
    assert routing_decision.action == "auto_reject"


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------


def test_exactly_at_approve_threshold_goes_to_review() -> None:
    # > 0.85 approves; == 0.85 falls into review band
    routing_decision = route(0.85)
    assert routing_decision.action == "human_review"


def test_just_above_approve_threshold_approves() -> None:
    routing_decision = route(0.851)
    assert routing_decision.action == "auto_approve"


def test_exactly_at_reject_threshold_goes_to_review() -> None:
    # >= 0.50 → review
    routing_decision = route(0.50)
    assert routing_decision.action == "human_review"


def test_just_below_reject_threshold_rejects() -> None:
    routing_decision = route(0.499)
    assert routing_decision.action == "auto_reject"


# ---------------------------------------------------------------------------
# RoutingDecision attributes
# ---------------------------------------------------------------------------


def test_decision_carries_confidence() -> None:
    routing_decision = route(0.72)
    assert routing_decision.confidence == 0.72


def test_decision_reason_is_non_empty() -> None:
    for confidence_score in (0.10, 0.60, 0.95):
        assert route(confidence_score).reason


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------


def test_custom_thresholds_are_respected() -> None:
    # Raise approve bar to 0.95
    routing_decision = route(0.90, auto_approve_threshold=0.95, auto_reject_threshold=0.50)
    assert routing_decision.action == "human_review"


def test_very_permissive_threshold_approves_all() -> None:
    routing_decision = route(0.10, auto_approve_threshold=0.0, auto_reject_threshold=0.0)
    assert routing_decision.action == "auto_approve"


# ---------------------------------------------------------------------------
# RoutingDecision is a Pydantic model
# ---------------------------------------------------------------------------


def test_routing_decision_is_pydantic_model() -> None:
    decision = route(0.70)
    assert isinstance(decision, RoutingDecision)


def test_routing_decision_is_immutable() -> None:
    """RoutingDecision uses frozen=True — attribute assignment must raise."""
    decision = route(0.70)
    with pytest.raises((TypeError, Exception)):
        decision.action = "auto_approve"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Parameterised action boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "confidence,expected_action",
    [
        (0.95, "auto_approve"),   # well above threshold
        (0.86, "auto_approve"),   # just above threshold (0.85 < 0.86)
        (0.85, "human_review"),   # exactly at threshold → review (not above)
        (0.70, "human_review"),   # midband
        (0.50, "human_review"),   # exactly at reject threshold → review (not below)
        (0.499, "auto_reject"),   # just below reject threshold
        (0.10, "auto_reject"),    # well below
    ],
    ids=[
        "well_above_approve",
        "just_above_approve",
        "at_approve_threshold",
        "midband",
        "at_reject_threshold",
        "just_below_reject",
        "well_below_reject",
    ],
)
def test_routing_action_for_confidence(confidence: float, expected_action: str) -> None:
    """route() produces the correct action for all key confidence values."""
    assert route(confidence).action == expected_action


@pytest.mark.parametrize(
    "confidence,approve_t,reject_t,expected_action",
    [
        (0.80, 0.75, 0.50, "auto_approve"),  # custom approve threshold
        (0.60, 0.75, 0.65, "auto_reject"),   # custom reject threshold
        (0.70, 0.75, 0.65, "human_review"),  # within custom band
        (1.00, 0.90, 0.50, "auto_approve"),  # perfect score
        (0.00, 0.85, 0.50, "auto_reject"),   # zero score
    ],
    ids=[
        "custom_approve_threshold",
        "custom_reject_threshold",
        "within_custom_band",
        "perfect_score",
        "zero_score",
    ],
)
def test_routing_with_custom_thresholds(
    confidence: float,
    approve_t: float,
    reject_t: float,
    expected_action: str,
) -> None:
    """route() respects custom threshold arguments correctly."""
    decision = route(confidence, auto_approve_threshold=approve_t, auto_reject_threshold=reject_t)
    assert decision.action == expected_action
