"""CRM integration clients (mock — CSV and JSONL file outputs).

Appends approved intake rows to a CSV (Google Sheets mock) and a JSONL
file (Airtable/CRM mock). Replace with live API clients when integrating
a real CRM system.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def append_sheet_row(csv_path: str, row: dict[str, Any]) -> None:
    """Append a row to the mock Sheets CSV export.

    Creates the file and writes a header row if it does not yet exist.

    Args:
        csv_path: Path to the CSV file (created if absent).
        row: Ordered dict of field names to values.
    """
    parent_dir = os.path.dirname(csv_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    file_exists = os.path.exists(csv_path)

    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    logger.info("Sheet row appended", extra={"csv_path": csv_path})


def append_airtable_row(jsonl_path: str, row: dict[str, Any]) -> None:
    """Append a row to the mock Airtable JSONL export.

    Args:
        jsonl_path: Path to the JSONL file (created if absent).
        row: Dict of field names to values.
    """
    parent_dir = os.path.dirname(jsonl_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(jsonl_path, "a", encoding="utf-8") as jsonl_file:
        jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")

    logger.info("Airtable row appended", extra={"jsonl_path": jsonl_path})
