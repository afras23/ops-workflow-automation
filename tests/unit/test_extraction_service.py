"""Tests for ExtractionService.

All tests use MockAIClient — no real API calls.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.core.exceptions import ExtractionError
from app.models.email import InboxMessage
from app.services.ai.client import MockAIClient
from app.services.extraction_service import ExtractionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service(response: str | None = None) -> ExtractionService:
    """Create an ExtractionService backed by a MockAIClient."""
    return ExtractionService(ai_client=MockAIClient(response=response))


def _message(
    *,
    body: str = "Purchase order for 2x ThinkPad laptops. Item: ThinkPad T14s, Qty: 2.",
    subject: str = "Purchase request",
    message_id: str = "msg_001",
) -> InboxMessage:
    """Build a test InboxMessage with sensible defaults."""
    return InboxMessage(
        message_id=message_id,
        **{"from": {"name": "Alice", "email": "alice@example.com"}},
        subject=subject,
        received_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        body=body,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_extraction_model() -> None:
    extraction_result = await _service().extract(_message())
    assert extraction_result.request_id
    assert extraction_result.request_type in (
        "purchase_request",
        "customer_issue",
        "ops_change",
        "general_inquiry",
        "other",
    )
    assert 0.0 <= extraction_result.confidence <= 1.0


@pytest.mark.asyncio
async def test_purchase_request_body_yields_purchase_type() -> None:
    extraction_result = await _service().extract(
        _message(body="Please purchase 3 monitors. Item: Dell 27in, Qty: 3.")
    )
    assert extraction_result.request_type == "purchase_request"


@pytest.mark.asyncio
async def test_issue_body_yields_customer_issue_type() -> None:
    extraction_result = await _service().extract(
        _message(
            body="Billing portal shows HTTP 500 error. Cannot access invoices.",
            subject="Billing error report",
        )
    )
    assert extraction_result.request_type == "customer_issue"


@pytest.mark.asyncio
async def test_requester_populated_from_message_envelope() -> None:
    """request_id, requester.name/email always come from the message, not the AI."""
    extraction_result = await _service().extract(_message())
    assert extraction_result.requester.name == "Alice"
    assert str(extraction_result.requester.email) == "alice@example.com"


@pytest.mark.asyncio
async def test_confidence_is_computed_not_from_ai() -> None:
    """The AI response has no confidence field — it must be computed by ExtractionService."""
    raw_response = json.dumps(
        {
            "request_type": "purchase_request",
            "priority": "high",
            "due_date": "2026-04-01",
            "company": "Acme",
            "description": "Purchase 2x laptops for the new starters joining next month.",
            "line_items": [{"item": "ThinkPad", "qty": 2}],
            "extraction_notes": [],
        }
    )
    extraction_result = await _service(response=raw_response).extract(_message())
    assert 0.0 < extraction_result.confidence <= 1.0


@pytest.mark.asyncio
async def test_line_items_parsed_correctly() -> None:
    raw_response = json.dumps(
        {
            "request_type": "purchase_request",
            "priority": "medium",
            "due_date": None,
            "company": None,
            "description": "Need office chairs.",
            "line_items": [{"item": "Herman Miller Aeron", "qty": 4}],
            "extraction_notes": [],
        }
    )
    extraction_result = await _service(response=raw_response).extract(_message())
    assert len(extraction_result.line_items) == 1
    assert extraction_result.line_items[0].item == "Herman Miller Aeron"
    assert extraction_result.line_items[0].qty == 4


# ---------------------------------------------------------------------------
# Request_id determinism
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_message_produces_same_request_id() -> None:
    test_message = _message()
    first_result = await _service().extract(test_message)
    second_result = await _service().extract(test_message)
    assert first_result.request_id == second_result.request_id


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_json_response_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError, match="non-JSON"):
        await _service(response="Sorry, I cannot process this.").extract(_message())


@pytest.mark.asyncio
async def test_json_with_invalid_enum_raises_extraction_error() -> None:
    raw_response = json.dumps(
        {
            "request_type": "NOT_A_VALID_TYPE",
            "priority": "high",
            "due_date": None,
            "company": None,
            "description": "Some request.",
            "line_items": [],
            "extraction_notes": [],
        }
    )
    with pytest.raises(ExtractionError, match="schema mismatch"):
        await _service(response=raw_response).extract(_message())


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_parsed() -> None:
    """The service must strip ```json ... ``` fences that some models emit."""
    inner = json.dumps(
        {
            "request_type": "ops_change",
            "priority": "medium",
            "due_date": None,
            "company": None,
            "description": "Update deployment config.",
            "line_items": [],
            "extraction_notes": [],
        }
    )
    fenced = f"```json\n{inner}\n```"
    extraction_result = await _service(response=fenced).extract(_message())
    assert extraction_result.request_type == "ops_change"


@pytest.mark.asyncio
async def test_ai_client_exception_raises_extraction_error() -> None:
    """Network/provider errors surface as ExtractionError."""

    class BrokenClient(MockAIClient):
        async def complete(  # type: ignore[override]
            self, system: str = "", user: str = "", *, prompt_version: str = ""
        ) -> str:
            raise ConnectionError("provider unavailable")

    broken_service = ExtractionService(ai_client=BrokenClient())
    with pytest.raises(ExtractionError, match="unavailable"):
        await broken_service.extract(_message())
