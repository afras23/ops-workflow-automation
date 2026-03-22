"""SQLAlchemy ORM models for database schema management via Alembic.

These models define the authoritative schema. The existing app.storage module
uses raw SQLite for runtime data access; these models exist so that Alembic can
generate and apply migrations consistently.

Tables:
  items         — processed email intake items (ReviewItem domain model)
  audit_log     — immutable audit trail for all state transitions
  llm_call_log  — per-request AI call telemetry (tokens, cost, latency)
"""

from __future__ import annotations

from sqlalchemy import Float, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Item(Base):
    """Processed email intake item.

    Corresponds to the items table and the ReviewItem domain model.
    """

    __tablename__ = "items"

    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    message_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_items_message_id", "message_id", unique=True),)


class AuditLogEntry(Base):
    """Immutable audit trail entry for every state transition.

    Corresponds to the audit_log table and the AuditEntry domain model.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_audit_item_id", "item_id"),)


class LlmCallLog(Base):
    """Per-request AI call telemetry for cost tracking and analysis.

    Stores tokens, cost, latency, and prompt version for every AI call made
    through the AnthropicClient. Enables cost analysis and capacity planning.
    """

    __tablename__ = "llm_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
