"""HTTP middleware for the ops workflow application.

CorrelationIDMiddleware
  - Reads X-Correlation-ID from the incoming request header (if present).
  - Generates a UUID4 when no header is supplied.
  - Sets the value in correlation_id_ctx so every log entry in that request
    automatically carries it (JSONFormatter reads from the same contextvar).
  - Echoes the value back as X-Correlation-ID in the response header.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import correlation_id_ctx


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Assign a unique correlation ID to every HTTP request.

    The ID is sourced from the incoming X-Correlation-ID header (allowing
    callers to propagate a trace across services) or generated fresh as a
    UUID4. It is stored in correlation_id_ctx for the duration of the
    request so all log entries produced in that context carry it, and it
    is returned to the caller in the X-Correlation-ID response header.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """Wrap a request with correlation ID injection and response header.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler in the chain.

        Returns:
            Response with X-Correlation-ID header attached.
        """
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        token = correlation_id_ctx.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
