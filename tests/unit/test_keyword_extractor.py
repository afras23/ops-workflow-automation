"""Tests for the keyword-based (rule-driven) extractor.

Uses real sample fixture files — no mocks, no AI calls.
"""

from __future__ import annotations

from pathlib import Path

from app.models.email import InboxMessage
from app.services.keyword_extractor import extract, load_schema_validator

_SCHEMA_PATH = "schemas/extraction_schema.json"
_FIXTURES = Path("tests/fixtures/sample_inputs")


def test_extraction_purchase_request() -> None:
    """Standard purchase request email extracts expected fields."""
    schema_validator = load_schema_validator(_SCHEMA_PATH)
    test_message = InboxMessage.model_validate_json(
        (_FIXTURES / "email_001.json").read_text(encoding="utf-8")
    )
    extraction_result = extract(test_message, schema_validator)

    assert extraction_result.request_type == "purchase_request"
    assert extraction_result.priority in ("high", "urgent")
    assert extraction_result.due_date == "2026-02-02"
    assert extraction_result.company is not None
    assert extraction_result.company.rstrip(".") == "ExampleCo"
    assert len(extraction_result.line_items) == 1
    assert extraction_result.confidence >= 0.7


def test_extraction_low_signal_goes_other() -> None:
    """Low-signal email is classified as 'other' with low confidence."""
    schema_validator = load_schema_validator(_SCHEMA_PATH)
    test_message = InboxMessage.model_validate_json(
        (_FIXTURES / "email_004_low_signal.json").read_text(encoding="utf-8")
    )
    extraction_result = extract(test_message, schema_validator)

    assert extraction_result.request_type == "other"
    assert extraction_result.confidence <= 0.6
