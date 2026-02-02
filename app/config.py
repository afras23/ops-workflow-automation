from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    slack_webhook_url: str | None
    confidence_threshold: float
    sqlite_path: str
    sheets_csv_path: str
    airtable_jsonl_path: str

def get_settings() -> Settings:
    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL") or None
    confidence_threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.78"))
    sqlite_path = os.getenv("SQLITE_PATH", "data/app.db")
    sheets_csv_path = os.getenv("SHEETS_CSV_PATH", "data/sheet_rows.csv")
    airtable_jsonl_path = os.getenv("AIRTABLE_JSONL_PATH", "data/airtable_rows.jsonl")
    return Settings(
        slack_webhook_url=slack_webhook_url,
        confidence_threshold=confidence_threshold,
        sqlite_path=sqlite_path,
        sheets_csv_path=sheets_csv_path,
        airtable_jsonl_path=airtable_jsonl_path,
    )
