"""FastAPI dependency injection providers.

Functions here are used with Depends() in route handlers or accessed
via app.state for services wired at startup. All stateful dependencies
(storage, AI client, services) are created once at startup and stored
on app.state to avoid per-request creation overhead.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import Request

from app.config import Settings, get_settings
from app.services.review_service import ReviewService
from app.services.workflow_service import WorkflowService
from app.storage import Storage

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_cached_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process).

    Returns:
        Validated Settings singleton.
    """
    return get_settings()


def get_storage(request: Request) -> Storage:
    """Return the Storage instance from app.state.

    Args:
        request: FastAPI request carrying the app instance.

    Returns:
        The Storage instance created at startup.
    """
    return request.app.state.storage


def get_workflow_service(request: Request) -> WorkflowService:
    """Return the WorkflowService instance from app.state.

    Args:
        request: FastAPI request carrying the app instance.

    Returns:
        The WorkflowService instance created at startup.
    """
    return request.app.state.workflow_service


def get_review_service(request: Request) -> ReviewService:
    """Return the ReviewService instance from app.state.

    Args:
        request: FastAPI request carrying the app instance.

    Returns:
        The ReviewService instance created at startup.
    """
    return request.app.state.review_service
