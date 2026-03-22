"""Slack notification client.

Sends PII-redacted summaries to a Slack incoming webhook. When no URL
is configured, logs the summary to stdout for local development.
"""

from __future__ import annotations

import logging

import httpx

from app.utils import redact_pii

logger = logging.getLogger(__name__)


async def send_slack_summary(webhook_url: str | None, text: str) -> None:
    """Send a redacted summary notification to Slack.

    Args:
        webhook_url: Slack incoming webhook URL. None triggers mock/log mode.
        text: Summary text — PII is automatically redacted before sending.

    Raises:
        httpx.HTTPStatusError: If the Slack webhook returns a non-2xx status.
    """
    safe_text = redact_pii(text)

    if not webhook_url:
        logger.info(
            "Mock Slack notification (no webhook configured)", extra={"preview": safe_text[:200]}
        )
        return

    async with httpx.AsyncClient(timeout=10) as slack_http_client:
        response = await slack_http_client.post(webhook_url, json={"text": safe_text})
        response.raise_for_status()

    logger.info("Slack notification sent", extra={"status_code": response.status_code})
