import os
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def _isolate_test_db(tmp_path, monkeypatch):
    # Force app to use a temporary sqlite db for each test run
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))

    # Also isolate output files
    monkeypatch.setenv("SHEETS_CSV_PATH", str(tmp_path / "sheet.csv"))
    monkeypatch.setenv("AIRTABLE_JSONL_PATH", str(tmp_path / "airtable.jsonl"))
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.78")

    # Ensure data folder isn't relied on
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
