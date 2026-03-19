"""Tests for ExtractionService.

All tests use MockAIClient — no real API calls.
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone

from app.models import InboxMessage
from app.services.ai_client import MockAIClient
from app.services.extraction import ExtractionError, ExtractionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _service(response: str | None = None) -> ExtractionService:
    return ExtractionService(ai_client=MockAIClient(response=response))


def _message(
    *,
    body: str = "Purchase order for 2x ThinkPad laptops. Item: ThinkPad T14s, Qty: 2.",
    subject: str = "Purchase request",
    message_id: str = "msg_001",
) -> InboxMessage:
    return InboxMessage(
        message_id=message_id,
        **{"from": {"name": "Alice", "email": "alice@example.com"}},
        subject=subject,
        received_at=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
        body=body,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_extraction_model():
    svc = _service()
    result = await svc.extract(_message())
    assert result.request_id  # computed from message fields
    assert result.request_type in ("purchase_request", "customer_issue", "ops_change", "general_inquiry", "other")
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_purchase_request_body_yields_purchase_type():
    svc = _service()
    result = await svc.extract(_message(body="Please purchase 3 monitors. Item: Dell 27in, Qty: 3."))
    assert result.request_type == "purchase_request"


@pytest.mark.asyncio
async def test_issue_body_yields_customer_issue_type():
    svc = _service()
    # Override subject too — the mock inspects the full user prompt (which includes subject)
    result = await svc.extract(_message(
        body="Billing portal shows HTTP 500 error. Cannot access invoices.",
        subject="Billing error report",
    ))
    assert result.request_type == "customer_issue"


@pytest.mark.asyncio
async def test_requester_populated_from_message_envelope():
    """request_id, requester.name/email always come from the message, not the AI."""
    svc = _service()
    msg = _message()
    result = await svc.extract(msg)
    assert result.requester.name == "Alice"
    assert str(result.requester.email) == "alice@example.com"


@pytest.mark.asyncio
async def test_confidence_is_computed_not_from_ai():
    """The AI response has no confidence field — it must be computed by ExtractionService."""
    raw = json.dumps({
        "request_type": "purchase_request",
        "priority": "high",
        "due_date": "2026-04-01",
        "company": "Acme",
        "description": "Purchase 2x laptops for the new starters joining next month.",
        "line_items": [{"item": "ThinkPad", "qty": 2}],
        "extraction_notes": [],
    })
    svc = _service(response=raw)
    result = await svc.extract(_message())
    # Confidence is always in [0, 1] and not 0.0 (placeholder would mean bug)
    assert 0.0 < result.confidence <= 1.0


@pytest.mark.asyncio
async def test_line_items_parsed_correctly():
    raw = json.dumps({
        "request_type": "purchase_request",
        "priority": "medium",
        "due_date": None,
        "company": None,
        "description": "Need office chairs.",
        "line_items": [{"item": "Herman Miller Aeron", "qty": 4}],
        "extraction_notes": [],
    })
    svc = _service(response=raw)
    result = await svc.extract(_message())
    assert len(result.line_items) == 1
    assert result.line_items[0].item == "Herman Miller Aeron"
    assert result.line_items[0].qty == 4


# ---------------------------------------------------------------------------
# Request_id determinism
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_same_message_produces_same_request_id():
    svc = _service()
    msg = _message()
    r1 = await svc.extract(msg)
    r2 = await svc.extract(msg)
    assert r1.request_id == r2.request_id


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_json_response_raises_extraction_error():
    svc = _service(response="Sorry, I cannot process this.")
    with pytest.raises(ExtractionError, match="non-JSON"):
        await svc.extract(_message())


@pytest.mark.asyncio
async def test_json_with_invalid_enum_raises_extraction_error():
    raw = json.dumps({
        "request_type": "NOT_A_VALID_TYPE",
        "priority": "high",
        "due_date": None,
        "company": None,
        "description": "Some request.",
        "line_items": [],
        "extraction_notes": [],
    })
    svc = _service(response=raw)
    with pytest.raises(ExtractionError, match="schema mismatch"):
        await svc.extract(_message())


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_parsed():
    """The service must strip ```json ... ``` fences some models emit."""
    inner = json.dumps({
        "request_type": "ops_change",
        "priority": "medium",
        "due_date": None,
        "company": None,
        "description": "Update deployment config.",
        "line_items": [],
        "extraction_notes": [],
    })
    fenced = f"```json\n{inner}\n```"
    svc = _service(response=fenced)
    result = await svc.extract(_message())
    assert result.request_type == "ops_change"


@pytest.mark.asyncio
async def test_ai_client_exception_raises_extraction_error():
    """Network/provider errors surface as ExtractionError."""
    class BrokenClient(MockAIClient):
        async def complete(self, _system: str = "", _user: str = "") -> str:  # type: ignore[override]
            raise ConnectionError("provider unavailable")

    svc = ExtractionService(ai_client=BrokenClient())
    with pytest.raises(ExtractionError, match="unavailable"):
        await svc.extract(_message())
