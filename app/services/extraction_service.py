"""AI extraction service.

Pipeline for a single message:
  build_prompt → call AI → parse JSON → validate schema → score confidence
  → return Extraction

ExtractionError (from app.core.exceptions) is raised on any failure in
this pipeline and should be caught by the caller to map to an HTTP 422.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import BaseAppError, ExtractionError
from app.models.email import AIExtractionOutput, Extraction, InboxMessage, Requester
from app.services.ai.client import AIClient
from app.services.ai.prompts import SYSTEM_PROMPT, VERSION, build_prompt
from app.services.confidence_service import compute_confidence
from app.utils import stable_id

logger = logging.getLogger(__name__)


class ExtractionService:
    """Orchestrates AI-powered field extraction for a single InboxMessage."""

    def __init__(self, ai_client: AIClient) -> None:
        """Initialise with an AI client.

        Args:
            ai_client: Provider-agnostic AI completion client.
        """
        self._ai = ai_client

    async def extract(self, message: InboxMessage) -> Extraction:
        """Extract structured fields from an InboxMessage.

        Pipeline: build prompt → call AI → parse JSON → validate schema
        → score confidence → return Extraction.

        Args:
            message: Validated inbox message.

        Returns:
            Extraction with all fields populated and confidence scored.

        Raises:
            ExtractionError: On AI failure, parse error, or schema validation failure.
        """
        input_hash = _hash_input(message.body)
        user_prompt = build_prompt(
            from_name=message.from_.name,
            from_email=str(message.from_.email),
            subject=message.subject,
            received_at=message.received_at.isoformat(),
            body=message.body,
        )

        raw_response = await self._call_ai(user_prompt, input_hash=input_hash)
        ai_output = self._parse_and_validate(raw_response, input_hash=input_hash)
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

    async def _call_ai(self, user_prompt: str, *, input_hash: str) -> str:
        """Call the AI provider and return the raw text response.

        Args:
            user_prompt: Rendered user-turn message.
            input_hash: Short digest for log correlation.

        Returns:
            Raw text response from the provider.

        Raises:
            BaseAppError: CostLimitExceeded / RetryableError propagate as-is.
            ExtractionError: On any other provider failure.
        """
        try:
            ai_result = await self._ai.complete(
                system=SYSTEM_PROMPT,
                user=user_prompt,
                prompt_version=VERSION,
            )
        except BaseAppError:
            raise
        except Exception as exc:
            logger.error(
                "AI provider call failed",
                extra={"input_hash": input_hash, "error": str(exc)},
            )
            raise ExtractionError(
                f"AI provider unavailable: {exc}",
                context={"input_hash": input_hash},
            ) from exc

        logger.debug(
            "AI response received",
            extra={
                "input_hash": input_hash,
                "response_length": len(ai_result.text),
                "tokens_in": ai_result.tokens_in,
                "tokens_out": ai_result.tokens_out,
                "cost_usd": ai_result.cost_usd,
                "latency_ms": round(ai_result.latency_ms, 1),
            },
        )
        return ai_result.text

    def _parse_and_validate(self, raw_response: str, *, input_hash: str) -> AIExtractionOutput:
        """Parse the AI response JSON and validate with Pydantic.

        Args:
            raw_response: Raw text from the AI provider.
            input_hash: Short digest for log correlation.

        Returns:
            Validated AIExtractionOutput.

        Raises:
            ExtractionError: If the response is not valid JSON or fails schema validation.
        """
        text = raw_response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            payload: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "AI response not valid JSON",
                extra={"input_hash": input_hash, "preview": raw_response[:200]},
            )
            raise ExtractionError(
                "AI returned non-JSON response",
                context={"input_hash": input_hash},
            ) from exc

        try:
            return AIExtractionOutput.model_validate(payload)
        except ValidationError as exc:
            logger.warning(
                "AI response failed schema validation",
                extra={"input_hash": input_hash, "errors": exc.errors()},
            )
            raise ExtractionError(
                f"AI output schema mismatch: {exc.error_count()} field(s) invalid",
                context={"input_hash": input_hash},
            ) from exc

    def _build_extraction(self, message: InboxMessage, ai_output: AIExtractionOutput) -> Extraction:
        """Combine AI output with message-envelope fields into a full Extraction.

        Args:
            message: Original inbox message (source of truth for requester fields).
            ai_output: Validated AI extraction output.

        Returns:
            Complete Extraction with request_id, requester, and confidence scored.
        """
        request_id = stable_id(message.message_id, str(message.from_.email), message.subject)
        requester = Requester(name=message.from_.name, email=message.from_.email)

        partial_extraction = Extraction(
            request_id=request_id,
            request_type=ai_output.request_type,
            priority=ai_output.priority,
            due_date=ai_output.due_date,
            company=ai_output.company,
            requester=requester,
            description=ai_output.description,
            line_items=ai_output.line_items,
            confidence=0.0,
            extraction_notes=ai_output.extraction_notes,
        )
        confidence_result = compute_confidence(partial_extraction)
        return partial_extraction.model_copy(update={"confidence": confidence_result.score})


def _hash_input(body: str) -> str:
    """Return a short SHA-256 hex digest of the email body for audit/dedup.

    Args:
        body: Raw email body text.

    Returns:
        16-character lowercase hex string.
    """
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
