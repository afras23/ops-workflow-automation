"""Parametrised unit tests for ExtractionService across email variations.

Each case drives a distinct input shape to verify that the extraction
pipeline handles the full range of real-world email content:
well-formed requests, missing fields, HTML markup, unicode, empty bodies,
and multi-line / very long payloads.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.email import InboxMessage, RequestType
from app.services.ai.client import MockAIClient
from app.services.extraction_service import ExtractionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _svc() -> ExtractionService:
    return ExtractionService(ai_client=MockAIClient())


def _msg(
    body: str,
    subject: str = "Test subject",
    message_id: str = "param_msg_001",
    sender_name: str = "Alice",
    sender_email: str = "alice@example.com",
) -> InboxMessage:
    return InboxMessage(
        message_id=message_id,
        **{"from": {"name": sender_name, "email": sender_email}},
        subject=subject,
        received_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        body=body,
    )


# ---------------------------------------------------------------------------
# Parametrised matrix — body → expected request type
# ---------------------------------------------------------------------------

_EXTRACTION_CASES: list[tuple[str, str, RequestType]] = [
    (
        "Please purchase 5 Logitech K380 keyboards. Item: K380, Qty: 5.",
        "Hardware purchase request",
        "purchase_request",
    ),
    (
        "We need to order 10 office chairs for the new hires starting Monday.",
        "Furniture order",
        "purchase_request",
    ),
    (
        "Billing portal throws HTTP 500 on every page load. Company: Northwind.",
        "Billing portal error",
        "customer_issue",
    ),
    (
        "Customer incident: users cannot access invoices, error on login page.",
        "Customer login incident",
        "customer_issue",
    ),
    (
        "Please update the API rate-limit config for the staging environment.",
        "Ops config change",
        "ops_change",
    ),
    (
        "We need to deploy the hotfix to production before the end of day.",
        "Deployment request",
        "ops_change",
    ),
    (
        "",
        "No content",
        "other",
    ),
    (
        "こんにちは、サポートが必要です。どうぞよろしく。",
        "Unicode request",
        "other",
    ),
    (
        "Hey, just checking in. Can you help when you get a chance?",
        "Casual inquiry",
        "other",
    ),
    (
        "<b>Buy</b> 3 <em>ThinkPad</em> laptops for the new engineering team.",
        "HTML-body purchase request",
        "purchase_request",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("body,subject,expected_type", _EXTRACTION_CASES)
async def test_extraction_classifies_email_correctly(
    body: str, subject: str, expected_type: RequestType
) -> None:
    """Each email variation is classified to the expected request type."""
    extraction = await _svc().extract(_msg(body, subject=subject))
    assert extraction.request_type == expected_type


# ---------------------------------------------------------------------------
# Field-level assertions for well-formed emails
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_well_formed_purchase_email_has_line_items() -> None:
    """A purchase email with Item:/Qty: yields at least one line item."""
    extraction = await _svc().extract(
        _msg(
            "Purchase order: Item: Dell XPS 15, Qty: 2. Needed by end of quarter.",
            subject="Equipment purchase",
        )
    )
    assert len(extraction.line_items) >= 1


@pytest.mark.asyncio
async def test_requester_comes_from_envelope_not_body() -> None:
    """Requester identity is always sourced from the message envelope."""
    extraction = await _svc().extract(
        _msg(
            "This email was sent by Mallory <attacker@evil.com>. Please purchase items.",
            sender_name="Bob",
            sender_email="bob@corp.com",
        )
    )
    assert extraction.requester.name == "Bob"
    assert str(extraction.requester.email) == "bob@corp.com"


@pytest.mark.asyncio
async def test_very_long_body_is_processed_without_error() -> None:
    """Bodies over 5 000 characters are accepted and classified without crashing."""
    long_body = "We have a billing portal error. HTTP 500 on every request. " + (
        "The system has been broken since the latest deployment. " * 100
    )
    extraction = await _svc().extract(_msg(long_body, subject="Extended incident report"))
    assert extraction.request_type in (
        "customer_issue",
        "purchase_request",
        "ops_change",
        "general_inquiry",
        "other",
    )
    assert 0.0 <= extraction.confidence <= 1.0


@pytest.mark.asyncio
async def test_missing_optional_fields_yield_valid_extraction() -> None:
    """An email with minimal fields (no company, no due date) still extracts cleanly."""
    extraction = await _svc().extract(
        _msg(
            "Please order some pens.",
            subject="Quick purchase",
        )
    )
    assert extraction.request_type == "purchase_request"
    assert extraction.company is None or isinstance(extraction.company, str)
    assert extraction.due_date is None or isinstance(extraction.due_date, str)


@pytest.mark.asyncio
async def test_numeric_only_body_does_not_crash() -> None:
    """A body containing only numbers falls through to 'other' without error."""
    extraction = await _svc().extract(_msg("12345 67890 00000", subject="Numbers only"))
    assert extraction.request_type == "other"


@pytest.mark.asyncio
async def test_multiline_body_is_accepted() -> None:
    """Multiline bodies with mixed content are processed correctly."""
    body = "\n".join(
        [
            "Hi there,",
            "",
            "We're experiencing a billing error on the portal.",
            "The error started on Monday morning.",
            "Company: ACME Corp",
            "",
            "Please investigate ASAP.",
            "",
            "Thanks,",
            "Support team",
        ]
    )
    extraction = await _svc().extract(_msg(body, subject="Billing portal support"))
    assert extraction.request_type == "customer_issue"
