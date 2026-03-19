"""AI extraction service.

Pipeline for a single message:
  build_prompt → call AI → parse JSON → validate schema → score confidence
  → return Extraction

Validation happens at two layers:
  1. Pydantic (AIExtractionOutput): field types and enum membership
  2. Business rules: description non-empty, requester populated

Raises ExtractionError (a ValueError subclass) on any unrecoverable failure
so the caller can map it to an HTTP 400 without leaking internal details.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from app.models import AIExtractionOutput, Extraction, InboxMessage, Requester
from app.prompts.email_extraction import SYSTEM_PROMPT, VERSION, build_prompt
from app.services.ai_client import AIClient
from app.services.confidence import compute_confidence
from app.utils import stable_id

logger = logging.getLogger(__name__)


class ExtractionError(ValueError):
    """Raised when extraction fails in a way the caller should surface as a 400."""


class ExtractionService:
    """Orchestrates AI-powered extraction for a single InboxMessage."""

    def __init__(self, ai_client: AIClient) -> None:
        self._ai = ai_client

    async def extract(self, message: InboxMessage) -> Extraction:
        """Extract structured fields from an InboxMessage.

        Args:
            message: Validated inbox message.

        Returns:
            Extraction with all fields populated and confidence scored.

        Raises:
            ExtractionError: On AI failure, parse error, or validation failure.
        """
        input_hash = _hash_input(message.body)
        user_prompt = build_prompt(
            from_name=message.from_.name,
            from_email=str(message.from_.email),
            subject=message.subject,
            received_at=message.received_at.isoformat(),
            body=message.body,
        )

        raw = await self._call_ai(user_prompt, input_hash=input_hash)
        ai_output = self._parse_and_validate(raw, input_hash=input_hash)
        extraction = self._build_extraction(message, ai_output)

        logger.info(
            "Extraction complete",
            extra={
                "input_hash": input_hash,
                "request_type": extraction.request_type,
                "confidence": extraction.confidence,
                "prompt_version": VERSION,
                "line_items_count": len(extraction.line_items),
            },
        )
        return extraction

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_ai(self, user_prompt: str, *, input_hash: str) -> str:
        """Call the AI provider and return the raw text response."""
        try:
            raw = await self._ai.complete(system=SYSTEM_PROMPT, user=user_prompt)
        except Exception as exc:
            logger.error(
                "AI provider call failed",
                extra={"input_hash": input_hash, "error": str(exc)},
            )
            raise ExtractionError(f"AI provider unavailable: {exc}") from exc

        logger.debug(
            "AI response received",
            extra={"input_hash": input_hash, "response_length": len(raw)},
        )
        return raw

    def _parse_and_validate(self, raw: str, *, input_hash: str) -> AIExtractionOutput:
        """Parse the AI response JSON and validate with Pydantic.

        Args:
            raw: Raw string returned by the AI provider.
            input_hash: Used for structured log context only.

        Returns:
            Validated AIExtractionOutput.

        Raises:
            ExtractionError: On JSON parse failure or schema mismatch.
        """
        # Strip accidental markdown code fences the model might emit
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            payload: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "AI response not valid JSON",
                extra={"input_hash": input_hash, "preview": raw[:200]},
            )
            raise ExtractionError("AI returned non-JSON response") from exc

        try:
            return AIExtractionOutput.model_validate(payload)
        except ValidationError as exc:
            logger.warning(
                "AI response failed schema validation",
                extra={"input_hash": input_hash, "errors": exc.errors()},
            )
            raise ExtractionError(f"AI output schema mismatch: {exc.error_count()} field(s) invalid") from exc

    def _build_extraction(self, message: InboxMessage, ai_output: AIExtractionOutput) -> Extraction:
        """Combine AI output with computed fields into a full Extraction.

        request_id and confidence are computed here — not by the AI.
        """
        request_id = stable_id(message.message_id, str(message.from_.email), message.subject)
        requester = Requester(name=message.from_.name, email=message.from_.email)

        # Build without confidence first so compute_confidence has the full object
        extraction = Extraction(
            request_id=request_id,
            request_type=ai_output.request_type,
            priority=ai_output.priority,
            due_date=ai_output.due_date,
            company=ai_output.company,
            requester=requester,
            description=ai_output.description,
            line_items=ai_output.line_items,
            confidence=0.0,  # placeholder; overwritten immediately below
            extraction_notes=ai_output.extraction_notes,
        )
        extraction = extraction.model_copy(update={"confidence": compute_confidence(extraction)})
        return extraction


def _hash_input(body: str) -> str:
    """Return a short SHA-256 hex digest of the email body for audit/dedup."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
