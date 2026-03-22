"""Tests for the confidence scoring service.

compute_confidence() is a pure function — no mocks, no I/O.

Score formula: completeness * 0.4 + type_compliance * 0.4 + ai_confidence * 0.2
"""

from __future__ import annotations

import pytest

from app.models.email import Extraction, LineItem, Requester
from app.services.confidence_service import ConfidenceResult, compute_confidence

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
# Return type
# ---------------------------------------------------------------------------


def test_compute_confidence_returns_confidence_result() -> None:
    result = compute_confidence(_extraction())
    assert isinstance(result, ConfidenceResult)


def test_confidence_result_has_all_components() -> None:
    result = compute_confidence(_extraction())
    assert 0.0 <= result.completeness_score <= 1.0
    assert 0.0 <= result.type_compliance_score <= 1.0
    assert 0.0 <= result.ai_confidence_score <= 1.0
    assert 0.0 <= result.score <= 1.0


# ---------------------------------------------------------------------------
# Request type scoring
# ---------------------------------------------------------------------------


def test_known_request_type_adds_score() -> None:
    with_type = _extraction(
        request_type="purchase_request", line_items=[LineItem(item="Chair", qty=1)]
    )
    without_type = _extraction(request_type="other")
    assert compute_confidence(with_type).score > compute_confidence(without_type).score


def test_other_request_type_reduces_score() -> None:
    other_extraction = _extraction(request_type="other", company=None, due_date=None)
    assert compute_confidence(other_extraction).score < 0.50


# ---------------------------------------------------------------------------
# Description substance
# ---------------------------------------------------------------------------


def test_long_description_increases_score() -> None:
    short_extraction = _extraction(description="Help me.")
    long_extraction = _extraction(description="A" * 150)
    assert compute_confidence(long_extraction).score > compute_confidence(short_extraction).score


def test_very_short_description_contributes_zero() -> None:
    minimal_extraction = _extraction(
        description="Hi", company=None, due_date=None, request_type="other"
    )
    assert compute_confidence(minimal_extraction).score < 0.30


# ---------------------------------------------------------------------------
# Requester completeness
# ---------------------------------------------------------------------------


def test_full_requester_scores_higher_than_email_only() -> None:
    full_requester = _extraction(requester=Requester(name="Jane", email="j@a.com"))
    email_only_requester = _extraction(requester=Requester(name="", email="j@a.com"))
    assert compute_confidence(full_requester).score > compute_confidence(email_only_requester).score


# ---------------------------------------------------------------------------
# Optional enrichment fields
# ---------------------------------------------------------------------------


def test_company_increases_score() -> None:
    with_company = _extraction(company="Acme")
    without_company = _extraction(company=None)
    assert compute_confidence(with_company).score > compute_confidence(without_company).score


def test_due_date_increases_score() -> None:
    with_due = _extraction(due_date="2026-04-01")
    without_due = _extraction(due_date=None)
    assert compute_confidence(with_due).score > compute_confidence(without_due).score


# ---------------------------------------------------------------------------
# Purchase-request line-item logic
# ---------------------------------------------------------------------------


def test_purchase_with_line_items_scores_high() -> None:
    purchase_with_items = _extraction(
        request_type="purchase_request",
        line_items=[LineItem(item="ThinkPad", qty=2)],
    )
    assert compute_confidence(purchase_with_items).score >= 0.85


def test_purchase_without_line_items_is_penalised() -> None:
    with_items = _extraction(
        request_type="purchase_request",
        line_items=[LineItem(item="ThinkPad", qty=2)],
    )
    without_items = _extraction(request_type="purchase_request", line_items=[])
    assert compute_confidence(with_items).score > compute_confidence(without_items).score


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
    assert compute_confidence(maximal_extraction).score <= 1.0


def test_score_never_below_zero() -> None:
    minimal_extraction = _extraction(
        request_type="purchase_request",
        line_items=[],
        description="",
        company=None,
        due_date=None,
    )
    assert compute_confidence(minimal_extraction).score >= 0.0


# ---------------------------------------------------------------------------
# Parameterised scenarios — 8 cases covering all field combinations
# ---------------------------------------------------------------------------

_FULL_ITEMS = [LineItem(item="ThinkPad", qty=2)]
_EMAIL_ONLY = Requester(name="", email="jane@acme.com")

_LONG_DESC = "A" * 150  # >= 100 chars → completeness desc = 0.40
_MID_DESC = "B" * 60  # 40–99 chars → completeness desc = 0.28
_SHORT_DESC = "Short"  # 5 chars < 15 → completeness desc = 0.00


@pytest.mark.parametrize(
    "overrides,expected_min,expected_max",
    [
        # 1. All fields complete, customer_issue (no line items needed) → high score
        (
            {"description": _LONG_DESC, "request_type": "customer_issue"},
            0.85,
            1.0,
        ),
        # 2. Purchase request with explicit line items → high score
        (
            {
                "request_type": "purchase_request",
                "line_items": _FULL_ITEMS,
                "description": _MID_DESC,
            },
            0.85,
            1.0,
        ),
        # 3. Purchase request missing line items → medium-low (penalised type compliance)
        (
            {"request_type": "purchase_request", "line_items": [], "description": _MID_DESC},
            0.40,
            0.72,
        ),
        # 4. "other" type, decent description, missing company/due_date → below reject threshold
        (
            {
                "request_type": "other",
                "company": None,
                "due_date": None,
                "description": _MID_DESC,
            },
            0.00,
            0.50,
        ),
        # 5. Empty description, "other" type, missing enrichment → very low
        (
            {
                "description": _SHORT_DESC,
                "request_type": "other",
                "company": None,
                "due_date": None,
            },
            0.00,
            0.30,
        ),
        # 6. Email-only requester (no name) → slightly lower than full requester
        (
            {"requester": _EMAIL_ONLY, "description": _MID_DESC},
            0.70,
            0.92,
        ),
        # 7. Many extraction notes (3) → lower AI confidence component
        (
            {
                "extraction_notes": ["ambiguity 1", "ambiguity 2", "ambiguity 3"],
                "description": _MID_DESC,
            },
            0.55,
            0.80,
        ),
        # 8. ops_change with no company or due date → review band
        (
            {
                "request_type": "ops_change",
                "company": None,
                "due_date": None,
                "description": _MID_DESC,
            },
            0.50,
            0.80,
        ),
    ],
    ids=[
        "all_fields_customer_issue",
        "purchase_with_items",
        "purchase_no_items",
        "other_type_no_enrichment",
        "empty_desc_other_type",
        "email_only_requester",
        "many_extraction_notes",
        "ops_change_no_enrichment",
    ],
)
def test_confidence_score_in_expected_range(
    overrides: dict,
    expected_min: float,
    expected_max: float,
) -> None:
    """Confidence score falls within the expected range for each scenario."""
    extraction = _extraction(**overrides)
    result = compute_confidence(extraction)
    assert expected_min <= result.score <= expected_max, (
        f"score={result.score} not in [{expected_min}, {expected_max}] "
        f"— components: completeness={result.completeness_score}, "
        f"type_compliance={result.type_compliance_score}, "
        f"ai_confidence={result.ai_confidence_score}"
    )


# ---------------------------------------------------------------------------
# AI confidence component
# ---------------------------------------------------------------------------


def test_zero_notes_gives_highest_ai_confidence() -> None:
    no_notes = _extraction(extraction_notes=[])
    one_note = _extraction(extraction_notes=["ambiguous priority"])
    assert compute_confidence(no_notes).ai_confidence_score > compute_confidence(one_note).ai_confidence_score


def test_three_notes_gives_lowest_ai_confidence() -> None:
    three_notes = _extraction(extraction_notes=["a", "b", "c"])
    two_notes = _extraction(extraction_notes=["a", "b"])
    assert compute_confidence(three_notes).ai_confidence_score < compute_confidence(two_notes).ai_confidence_score


# ---------------------------------------------------------------------------
# Scoring notes audit trail
# ---------------------------------------------------------------------------


def test_other_type_produces_unclassified_note() -> None:
    result = compute_confidence(_extraction(request_type="other"))
    assert any("classified" in note for note in result.notes)


def test_purchase_no_items_produces_missing_line_items_note() -> None:
    result = compute_confidence(_extraction(request_type="purchase_request", line_items=[]))
    assert any("line items" in note for note in result.notes)


def test_missing_company_produces_note() -> None:
    result = compute_confidence(_extraction(company=None))
    assert any("company" in note for note in result.notes)
