"""FastAPI application factory.

Creates and configures the application with:
- Structured JSON logging (via configure_logging)
- Lifespan context for startup/shutdown resource management
- CORS middleware
- Structured error handler for BaseAppError
- All API routers under /api/v1

Business logic lives in app/services/; routes stay thin.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import audit, batch, health, process, review
from app.config import get_settings
from app.core.exceptions import BaseAppError
from app.core.logging_config import configure_logging, correlation_id_ctx
from app.services.ai.client import CircuitBreaker, DailyCostTracker, get_ai_client
from app.services.extraction_service import ExtractionService
from app.services.review_service import ReviewService
from app.services.workflow_service import WorkflowService
from app.storage import Storage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown resources.

    Initialises storage, AI client, and service instances on startup.
    Resources are stored on app.state so routes can access them via Request.

    Args:
        application: The FastAPI application instance.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    storage = Storage(settings.sqlite_path)
    cost_tracker = DailyCostTracker()
    circuit_breaker = CircuitBreaker()
    ai_client = get_ai_client(settings, cost_tracker=cost_tracker, circuit_breaker=circuit_breaker)
    extraction_service = ExtractionService(ai_client=ai_client)

    application.state.storage = storage
    application.state.workflow_service = WorkflowService(
        storage=storage,
        settings=settings,
        extraction_service=extraction_service,
    )
    application.state.review_service = ReviewService(
        storage=storage,
        settings=settings,
    )

    logger.info(
        "Application started",
        extra={
            "app_env": settings.app_env,
            "ai_provider": settings.ai_provider,
            "auto_approve_threshold": settings.auto_approve_threshold,
        },
    )

    yield

    logger.info("Application shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application with all routers and middleware attached.
    """
    application = FastAPI(
        title="Ops Workflow Automation",
        version="1.0.0",
        description=(
            "AI-powered ops intake pipeline with confidence scoring, "
            "three-way routing, and human review."
        ),
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(BaseAppError)
    async def app_error_handler(request: Request, exc: BaseAppError) -> JSONResponse:
        """Map BaseAppError subclasses to structured JSON error responses."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "context": exc.context,
                },
                "metadata": {"correlation_id": correlation_id_ctx.get("")},
            },
        )

    prefix = "/api/v1"
    application.include_router(health.router, prefix=prefix)
    application.include_router(process.router, prefix=prefix)
    application.include_router(review.router, prefix=prefix)
    application.include_router(audit.router, prefix=prefix)
    application.include_router(batch.router, prefix=prefix)

    return application


app = create_app()
