"""Tests for the routing service.

route() is a pure function — no mocks, no I/O.
"""

from __future__ import annotations

from app.services.routing_service import route

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
