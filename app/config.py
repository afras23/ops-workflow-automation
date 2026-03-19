"""Application configuration via Pydantic Settings.

Reads from environment variables and optional .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Integrations
    slack_webhook_url: str | None = None

    # AI provider: "anthropic" or "mock"
    ai_provider: str = "mock"
    anthropic_api_key: str | None = None
    ai_model: str = "claude-sonnet-4-6"

    # Routing thresholds
    auto_approve_threshold: float = 0.85
    auto_reject_threshold: float = 0.50

    # Storage
    sqlite_path: str = "data/app.db"
    sheets_csv_path: str = "data/sheet_rows.csv"
    airtable_jsonl_path: str = "data/airtable_rows.jsonl"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()
