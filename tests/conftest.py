"""Shared pytest fixtures for all test modules.

The _isolate_test_db fixture runs before every test (autouse=True) and
redirects all storage paths to temporary directories so tests never share
state or leave artefacts in the project's data/ directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect storage to a per-test temporary directory.

    Patches env vars before any app module imports within the test function,
    ensuring each test gets a fresh SQLite database and output files.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("SHEETS_CSV_PATH", str(tmp_path / "sheet.csv"))
    monkeypatch.setenv("AIRTABLE_JSONL_PATH", str(tmp_path / "airtable.jsonl"))
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("APP_ENV", "test")
