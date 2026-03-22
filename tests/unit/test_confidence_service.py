"""Tests for the confidence scoring service.

compute_confidence() is a pure function — no mocks, no I/O.
"""

from __future__ import annotations

from app.models.email import Extraction, LineItem, Requester
from app.services.confidence_service import compute_confidence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extraction(**overrides) -> Extraction:
    """Build a complete Extraction; keyword args override defaults."""
    defaults = dict(
        request_id="abc123",
        request_type="customer_issue",
        priority="high",
        due_date="2026-04-01",
        company="Acme Corp",
        requester=Requester(name="Jane Smith", email="jane@acme.com"),
        description=(
            "Customer reports HTTP 500 on the billing portal. "
            "Cannot access invoices since this morning."
        ),
        line_items=[],
        confidence=0.0,
        extraction_notes=[],
    )
    defaults.update(overrides)
    return Extraction(**defaults)


# ---------------------------------------------------------------------------
# Request type scoring
# ---------------------------------------------------------------------------


def test_known_request_type_adds_score() -> None:
    with_type = _extraction(
        request_type="purchase_request", line_items=[LineItem(item="Chair", qty=1)]
    )
    without_type = _extraction(request_type="other")
    assert compute_confidence(with_type) > compute_confidence(without_type)


def test_other_request_type_reduces_score() -> None:
    other_extraction = _extraction(request_type="other", company=None, due_date=None)
    assert compute_confidence(other_extraction) < 0.50


# ---------------------------------------------------------------------------
# Description substance
# ---------------------------------------------------------------------------


def test_long_description_increases_score() -> None:
    short_extraction = _extraction(description="Help me.")
    long_extraction = _extraction(description="A" * 150)
    assert compute_confidence(long_extraction) > compute_confidence(short_extraction)


def test_very_short_description_contributes_zero() -> None:
    minimal_extraction = _extraction(
        description="Hi", company=None, due_date=None, request_type="other"
    )
    assert compute_confidence(minimal_extraction) < 0.30


# ---------------------------------------------------------------------------
# Requester completeness
# ---------------------------------------------------------------------------


def test_full_requester_scores_higher_than_email_only() -> None:
    full_requester = _extraction(requester=Requester(name="Jane", email="j@a.com"))
    email_only_requester = _extraction(requester=Requester(name="", email="j@a.com"))
    assert compute_confidence(full_requester) > compute_confidence(email_only_requester)


# ---------------------------------------------------------------------------
# Optional enrichment fields
# ---------------------------------------------------------------------------


def test_company_increases_score() -> None:
    with_company = _extraction(company="Acme")
    without_company = _extraction(company=None)
    assert compute_confidence(with_company) > compute_confidence(without_company)


def test_due_date_increases_score() -> None:
    with_due = _extraction(due_date="2026-04-01")
    without_due = _extraction(due_date=None)
    assert compute_confidence(with_due) > compute_confidence(without_due)


# ---------------------------------------------------------------------------
# Purchase-request line-item logic
# ---------------------------------------------------------------------------


def test_purchase_with_line_items_scores_high() -> None:
    purchase_with_items = _extraction(
        request_type="purchase_request",
        line_items=[LineItem(item="ThinkPad", qty=2)],
    )
    assert compute_confidence(purchase_with_items) >= 0.85


def test_purchase_without_line_items_is_penalised() -> None:
    with_items = _extraction(
        request_type="purchase_request",
        line_items=[LineItem(item="ThinkPad", qty=2)],
    )
    without_items = _extraction(request_type="purchase_request", line_items=[])
    assert compute_confidence(with_items) > compute_confidence(without_items)


# ---------------------------------------------------------------------------
# Score bounds
# ---------------------------------------------------------------------------


def test_score_never_exceeds_one() -> None:
    maximal_extraction = _extraction(
        request_type="purchase_request",
        priority="urgent",
        due_date="2026-04-01",
        company="BigCo",
        description="A" * 200,
        line_items=[LineItem(item="X", qty=10)],
    )
    assert compute_confidence(maximal_extraction) <= 1.0


def test_score_never_below_zero() -> None:
    minimal_extraction = _extraction(
        request_type="purchase_request",
        line_items=[],
        description="",
        company=None,
        due_date=None,
    )
    assert compute_confidence(minimal_extraction) >= 0.0
