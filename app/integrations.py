from __future__ import annotations

import csv
import json
import os
from typing import Any
import httpx

from app.utils import redact_pii

async def send_slack_summary(webhook_url: str | None, text: str) -> None:
    safe_text = redact_pii(text)
    if not webhook_url:
        print(f"[MOCK SLACK] {safe_text}")
        return

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json={"text": safe_text})
        resp.raise_for_status()

def append_sheet_row(csv_path: str, row: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)

def append_airtable_row(jsonl_path: str, row: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
