"""FastAPI application factory.

Initialises settings, storage, AI client, and the workflow service,
then mounts all routers under /api/v1. Business logic lives in
app/services/; routes stay thin.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.routes import health, ingest, items
from app.services.ai_client import get_ai_client
from app.services.extraction import ExtractionService
from app.services.workflow import WorkflowService
from app.storage import Storage


def create_app() -> FastAPI:
    settings = get_settings()
    storage = Storage(settings.sqlite_path)
    ai_client = get_ai_client(settings)
    extraction_service = ExtractionService(ai_client=ai_client)
    service = WorkflowService(
        storage=storage,
        settings=settings,
        extraction_service=extraction_service,
    )

    application = FastAPI(
        title="Ops Workflow Automation",
        version="1.0.0",
        description="AI-powered ops intake pipeline with confidence scoring and human review.",
    )

    application.state.storage = storage
    application.state.workflow_service = service

    application.include_router(health.router, prefix="/api/v1")
    application.include_router(ingest.router, prefix="/api/v1")
    application.include_router(items.router, prefix="/api/v1")

    return application


app = create_app()
