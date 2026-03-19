"""Tests for routing logic.

route() is a pure function — no mocks, no I/O.
"""

import pytest
from app.services.routing import RoutingDecision, route


# ---------------------------------------------------------------------------
# Core three-way routing
# ---------------------------------------------------------------------------

def test_high_confidence_auto_approves():
    d = route(0.90)
    assert d.action == "auto_approve"


def test_mid_confidence_goes_to_review():
    d = route(0.70)
    assert d.action == "human_review"


def test_low_confidence_auto_rejects():
    d = route(0.30)
    assert d.action == "auto_reject"


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------

def test_exactly_at_approve_threshold_goes_to_review():
    # > 0.85 approves; == 0.85 falls into review band
    d = route(0.85)
    assert d.action == "human_review"


def test_just_above_approve_threshold_approves():
    d = route(0.851)
    assert d.action == "auto_approve"


def test_exactly_at_reject_threshold_goes_to_review():
    # >= 0.50 → review
    d = route(0.50)
    assert d.action == "human_review"


def test_just_below_reject_threshold_rejects():
    d = route(0.499)
    assert d.action == "auto_reject"


# ---------------------------------------------------------------------------
# RoutingDecision attributes
# ---------------------------------------------------------------------------

def test_decision_carries_confidence():
    d = route(0.72)
    assert d.confidence == 0.72


def test_decision_reason_is_non_empty():
    for confidence in (0.10, 0.60, 0.95):
        assert route(confidence).reason


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------

def test_custom_thresholds_are_respected():
    # Raise approve bar to 0.95
    d = route(0.90, auto_approve_threshold=0.95, auto_reject_threshold=0.50)
    assert d.action == "human_review"


def test_very_permissive_threshold_approves_all():
    d = route(0.10, auto_approve_threshold=0.0, auto_reject_threshold=0.0)
    assert d.action == "auto_approve"
