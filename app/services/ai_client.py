"""AI client abstraction.

Two implementations:
- AnthropicClient  — real Claude API calls (ai_provider=anthropic)
- MockAIClient     — returns keyword-inferred canned JSON (ai_provider=mock)

Tests always use MockAIClient. Production sets ANTHROPIC_API_KEY and
AI_PROVIDER=anthropic in the environment.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from app.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canned mock responses — realistic enough to exercise the full pipeline
# ---------------------------------------------------------------------------

_MOCK_PURCHASE = {
    "request_type": "purchase_request",
    "priority": "high",
    "due_date": "2026-03-31",
    "company": "Acme Corp",
    "description": "Purchase request for 2x ThinkPad T14s laptops for the engineering team.",
    "line_items": [{"item": "ThinkPad T14s", "qty": 2}],
    "extraction_notes": ["mock extraction — purchase_request keyword matched"],
}

_MOCK_ISSUE = {
    "request_type": "customer_issue",
    "priority": "urgent",
    "due_date": None,
    "company": "Northwind Traders",
    "description": "Customer reporting HTTP 500 error on billing portal. Cannot access invoices.",
    "line_items": [],
    "extraction_notes": ["mock extraction — customer_issue keyword matched"],
}

_MOCK_OPS = {
    "request_type": "ops_change",
    "priority": "medium",
    "due_date": None,
    "company": None,
    "description": "Request to update deployment configuration for the staging environment.",
    "line_items": [],
    "extraction_notes": ["mock extraction — ops_change keyword matched"],
}

_MOCK_VAGUE = {
    "request_type": "other",
    "priority": "medium",
    "due_date": None,
    "company": None,
    "description": "Unclassified request with insufficient context.",
    "line_items": [],
    "extraction_notes": ["mock extraction — no keyword match, low confidence expected"],
}


class AIClient(ABC):
    """Protocol for AI completion providers."""

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Send a prompt and return the raw text response."""


class MockAIClient(AIClient):
    """Returns canned JSON responses based on keyword matching.

    Keyword priority: purchase > issue/billing > change/update > default.
    Inject a custom ``response`` to override for specific test cases.
    """

    def __init__(self, response: str | None = None) -> None:
        self._fixed_response = response

    async def complete(self, system: str, user: str) -> str:
        if self._fixed_response is not None:
            return self._fixed_response

        lower = user.lower()
        if any(kw in lower for kw in ("purchase", "order", "item:", "buy", "procure")):
            payload = _MOCK_PURCHASE
        elif any(kw in lower for kw in ("error", "issue", "billing", "incident", "500", "bug")):
            payload = _MOCK_ISSUE
        elif any(kw in lower for kw in ("change", "update", "deploy", "config")):
            payload = _MOCK_OPS
        else:
            payload = _MOCK_VAGUE

        logger.debug("MockAIClient returning canned response", extra={"request_type": payload["request_type"]})
        return json.dumps(payload)


class AnthropicClient(AIClient):
    """Async Claude API client via the Anthropic SDK."""

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # lazy import — only required when provider=anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text  # type: ignore[union-attr]


def get_ai_client(settings: Settings) -> AIClient:
    """Return the appropriate AI client for the current configuration."""
    if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
        logger.info("Using AnthropicClient", extra={"model": settings.ai_model})
        return AnthropicClient(api_key=settings.anthropic_api_key, model=settings.ai_model)

    logger.info("Using MockAIClient (ai_provider=%s)", settings.ai_provider)
    return MockAIClient()
