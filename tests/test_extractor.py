import json
from pathlib import Path
from app.extractor import load_schema_validator, extract
from app.models import InboxMessage

def test_extraction_purchase_request():
    schema_validator = load_schema_validator("schemas/extraction_schema.json")
    msg = InboxMessage.model_validate_json(Path("samples/inbox/email_001.json").read_text(encoding="utf-8"))
    ex = extract(msg, schema_validator)
    assert ex.request_type == "purchase_request"
    assert ex.priority in ("high", "urgent")
    assert ex.due_date == "2026-02-02"
    assert ex.company.rstrip(".") == "ExampleCo"
    ''' or: assert ex.company in ("ExampleCo", "ExampleCo.")'''
    assert len(ex.line_items) == 1
    assert ex.confidence >= 0.7

def test_extraction_low_signal_goes_other():
    schema_validator = load_schema_validator("schemas/extraction_schema.json")
    msg = InboxMessage.model_validate_json(Path("samples/inbox/email_004_low_signal.json").read_text(encoding="utf-8"))
    ex = extract(msg, schema_validator)
    assert ex.request_type == "other"
    assert ex.confidence <= 0.6
