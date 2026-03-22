"""Application configuration via Pydantic Settings.

All configuration is sourced from environment variables (with .env fallback).
No hardcoded values — every threshold and connection string is configurable.
See .env.example for descriptions of all available variables.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings validated at startup from environment variables."""

    # Environment
    app_env: str = "development"
    log_level: str = "INFO"

    # AI provider: "anthropic" or "mock"
    ai_provider: str = "mock"
    anthropic_api_key: str | None = None
    ai_model: str = "claude-sonnet-4-6"

    # Cost controls (AI features must degrade gracefully at this limit)
    max_daily_cost_usd: float = 10.0

    # Routing confidence thresholds
    auto_approve_threshold: float = 0.85
    auto_reject_threshold: float = 0.50

    # Storage paths
    sqlite_path: str = "data/app.db"
    sheets_csv_path: str = "data/sheet_rows.csv"
    airtable_jsonl_path: str = "data/airtable_rows.jsonl"

    # Integrations
    slack_webhook_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    """Return a Settings instance populated from the environment.

    Returns:
        Validated Settings with all configuration values.
    """
    return Settings()
