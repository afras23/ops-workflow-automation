"""Application-wide constants.

Values that are fixed regardless of environment and would be opaque as
magic numbers inline. Configuration that varies by environment belongs
in app/config.py instead.
"""

from __future__ import annotations

# Routing confidence thresholds (overridable via Settings)
DEFAULT_AUTO_APPROVE_THRESHOLD: float = 0.85
DEFAULT_AUTO_REJECT_THRESHOLD: float = 0.50

# AI extraction limits
MAX_PROMPT_BODY_CHARS: int = 10_000
AI_MAX_TOKENS: int = 1024

# ID generation
STABLE_ID_LENGTH: int = 16

# Cost tracking — USD per 1M tokens (Claude Sonnet, 2026-Q1 pricing)
CLAUDE_SONNET_INPUT_COST_PER_1M: float = 3.00
CLAUDE_SONNET_OUTPUT_COST_PER_1M: float = 15.00

# Audit event type identifiers
EVENT_INGESTED: str = "ingested"
EVENT_INGEST_FAILED: str = "ingest_failed"
EVENT_APPROVED: str = "approved"
EVENT_REJECTED: str = "rejected"
EVENT_DESTINATIONS_WRITTEN: str = "destinations_written"
EVENT_SLACK_NOTIFIED: str = "slack_notified"

# Actor name for automated system events
ACTOR_SYSTEM: str = "system"
