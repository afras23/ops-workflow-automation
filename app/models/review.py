"""Pydantic models for review queue operations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReviewDecision(BaseModel):
    """Result of applying a human review decision to a pending item."""

    ok: bool
    status: Literal["approved", "rejected"]
