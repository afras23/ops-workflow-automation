"""Tests for confidence scoring.

compute_confidence() is a pure function — no mocks, no I/O.
"""

import pytest
from app.models import Extraction, LineItem, Requester
from app.services.confidence import compute_confidence


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _extraction(**overrides) -> Extraction:
    """Build a baseline complete Extraction; keyword args override any field."""
    defaults = dict(
        request_id="abc123",
        request_type="customer_issue",
        priority="high",
        due_date="2026-04-01",
        company="Acme Corp",
        requester=Requester(name="Jane Smith", email="jane@acme.com"),
        description="Customer reports HTTP 500 on the billing portal. Cannot access invoices since this morning.",
        line_items=[],
        confidence=0.0,
        extraction_notes=[],
    )
    defaults.update(overrides)
    return Extraction(**defaults)


# ---------------------------------------------------------------------------
# Type known → base score
# ---------------------------------------------------------------------------

def test_known_request_type_adds_score():
    e = _extraction(request_type="purchase_request", line_items=[LineItem(item="Chair", qty=1)])
    assert compute_confidence(e) > compute_confidence(_extraction(request_type="other"))


def test_other_request_type_reduces_score():
    e = _extraction(request_type="other", company=None, due_date=None)
    assert compute_confidence(e) < 0.50


# ---------------------------------------------------------------------------
# Description substance
# ---------------------------------------------------------------------------

def test_long_description_increases_score():
    short = _extraction(description="Help me.")
    long = _extraction(description="A" * 150)
    assert compute_confidence(long) > compute_confidence(short)


def test_very_short_description_contributes_zero():
    e = _extraction(description="Hi", company=None, due_date=None, request_type="other")
    score = compute_confidence(e)
    assert score < 0.30  # type penalty + no description + no enrichment


# ---------------------------------------------------------------------------
# Requester completeness
# ---------------------------------------------------------------------------

def test_full_requester_scores_higher_than_email_only():
    full = _extraction(requester=Requester(name="Jane", email="j@a.com"))
    email_only = _extraction(requester=Requester(name="", email="j@a.com"))
    assert compute_confidence(full) > compute_confidence(email_only)


# ---------------------------------------------------------------------------
# Optional enrichment fields
# ---------------------------------------------------------------------------

def test_company_increases_score():
    with_co = _extraction(company="Acme")
    without_co = _extraction(company=None)
    assert compute_confidence(with_co) > compute_confidence(without_co)


def test_due_date_increases_score():
    with_due = _extraction(due_date="2026-04-01")
    without_due = _extraction(due_date=None)
    assert compute_confidence(with_due) > compute_confidence(without_due)


# ---------------------------------------------------------------------------
# Purchase-request line-item logic
# ---------------------------------------------------------------------------

def test_purchase_with_line_items_scores_high():
    e = _extraction(
        request_type="purchase_request",
        line_items=[LineItem(item="ThinkPad", qty=2)],
    )
    assert compute_confidence(e) >= 0.85


def test_purchase_without_line_items_is_penalised():
    with_items = _extraction(
        request_type="purchase_request",
        line_items=[LineItem(item="ThinkPad", qty=2)],
    )
    without_items = _extraction(request_type="purchase_request", line_items=[])
    assert compute_confidence(with_items) > compute_confidence(without_items)


# ---------------------------------------------------------------------------
# Score bounds
# ---------------------------------------------------------------------------

def test_score_never_exceeds_one():
    e = _extraction(
        request_type="purchase_request",
        priority="urgent",
        due_date="2026-04-01",
        company="BigCo",
        description="A" * 200,
        line_items=[LineItem(item="X", qty=10)],
    )
    assert compute_confidence(e) <= 1.0


def test_score_never_below_zero():
    e = _extraction(
        request_type="purchase_request",  # purchase penalty
        line_items=[],
        description="",
        company=None,
        due_date=None,
    )
    assert compute_confidence(e) >= 0.0
