"""Raw SQLite storage layer.

All runtime data access goes through this class. Schema is defined as a
CREATE TABLE IF NOT EXISTS script so tests can initialise fresh databases
without running Alembic migrations.

WAL journal mode is enabled on init for concurrent-write safety under
asyncio.gather-based batch processing.

Tables:
  items        — processed email intake items
  audit_log    — immutable audit trail
  llm_call_log — per-request AI call telemetry
  batch_jobs   — batch ingest job progress records
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.utils import now_utc_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  message_id TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL,
  extraction_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_call_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  tokens_in INTEGER NOT NULL,
  tokens_out INTEGER NOT NULL,
  cost_usd REAL NOT NULL,
  latency_ms REAL NOT NULL,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_items_message_id ON items(message_id);
CREATE INDEX IF NOT EXISTS idx_audit_item_id ON audit_log(item_id);

CREATE TABLE IF NOT EXISTS batch_jobs (
  job_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  total INTEGER NOT NULL,
  processed INTEGER NOT NULL DEFAULT 0,
  succeeded INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class Storage:
    """SQLite-backed storage for items, audit events, and LLM call logs."""

    def __init__(self, path: str) -> None:
        """Initialise storage and ensure schema exists.

        Args:
            path: Filesystem path for the SQLite database file.
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    def get_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        """Return the item row matching message_id, or None.

        Args:
            message_id: Source email message identifier.

        Returns:
            Row as a dict, or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE message_id = ?", (message_id,)).fetchone()
            return dict(row) if row else None

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        """Return the item row matching item_id, or None.

        Args:
            item_id: Unique item identifier.

        Returns:
            Row as a dict, or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
            return dict(row) if row else None

    def list_items(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return all items, optionally filtered by status.

        Args:
            status: Optional status filter (e.g. 'pending_review').

        Returns:
            List of item rows as dicts, ordered by created_at descending.
        """
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM items WHERE status = ? ORDER BY created_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM items ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def list_items_paginated(
        self, page: int, page_size: int, status: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a page of items and the total count.

        Args:
            page: 1-based page number.
            page_size: Number of items per page.
            status: Optional status filter.

        Returns:
            Tuple of (page rows as dicts, total matching row count).
        """
        offset = (page - 1) * page_size
        with self._conn() as conn:
            if status:
                total = conn.execute(
                    "SELECT COUNT(*) FROM items WHERE status = ?", (status,)
                ).fetchone()[0]
                rows = conn.execute(
                    "SELECT * FROM items WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, page_size, offset),
                ).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
                rows = conn.execute(
                    "SELECT * FROM items ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (page_size, offset),
                ).fetchall()
            return [dict(r) for r in rows], total

    def create_item(
        self, item_id: str, message_id: str, status: str, confidence: float, extraction: dict
    ) -> None:
        """Insert a new item row.

        Args:
            item_id: Unique item identifier.
            message_id: Source email message identifier.
            status: Initial routing status.
            confidence: Extraction confidence score.
            extraction: Full extraction dict (serialised to JSON).
        """
        created = now_utc_iso()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO items(item_id, message_id, status, confidence, extraction_json, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (item_id, message_id, status, confidence, json.dumps(extraction), created, created),
            )

    def update_status(self, item_id: str, status: str) -> None:
        """Update the status of an existing item.

        Args:
            item_id: Unique item identifier.
            status: New status value.
        """
        updated = now_utc_iso()
        with self._conn() as conn:
            conn.execute(
                "UPDATE items SET status = ?, updated_at = ? WHERE item_id = ?",
                (status, updated, item_id),
            )

    def write_audit(self, item_id: str, event_type: str, actor: str, details: dict) -> None:
        """Append an audit event for an item.

        Args:
            item_id: Item the event belongs to.
            event_type: Category of the event (e.g. 'approved', 'ingested').
            actor: Who or what triggered the event (user ID or 'system').
            details: Arbitrary event payload (serialised to JSON).
        """
        created = now_utc_iso()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO audit_log(item_id, event_type, actor, details_json, created_at) VALUES(?,?,?,?,?)",
                (item_id, event_type, actor, json.dumps(details), created),
            )

    def list_audit(self, item_id: str) -> list[dict[str, Any]]:
        """Return all audit events for a specific item.

        Args:
            item_id: Item to retrieve audit events for.

        Returns:
            List of audit rows ordered by id ascending.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, item_id, event_type, actor, details_json, created_at FROM audit_log WHERE item_id = ? ORDER BY id ASC",
                (item_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def metrics_snapshot(self) -> dict[str, Any]:
        """Return a point-in-time metrics snapshot from the database.

        Gathers all metrics in a single database connection to minimise
        latency. The llm_call_log averages are 0.0 when no AI calls have
        been recorded (mock mode or fresh database).

        Returns:
            Dict with processed_today, success_rate, avg_latency_ms,
            avg_cost_usd, and queue_depth keys.
        """
        today_prefix = datetime.now(UTC).isoformat()[:10]  # "YYYY-MM-DD"
        with self._conn() as conn:
            processed_today: int = conn.execute(
                "SELECT COUNT(*) FROM items WHERE created_at LIKE ?",
                (f"{today_prefix}%",),
            ).fetchone()[0]

            approved: int = conn.execute(
                "SELECT COUNT(*) FROM items WHERE status = 'approved'"
            ).fetchone()[0]
            rejected: int = conn.execute(
                "SELECT COUNT(*) FROM items WHERE status = 'rejected'"
            ).fetchone()[0]
            total_decided = approved + rejected
            success_rate = round(approved / total_decided, 4) if total_decided else 0.0

            avg_latency_ms: float = (
                conn.execute("SELECT AVG(latency_ms) FROM llm_call_log").fetchone()[0] or 0.0
            )
            avg_cost_usd: float = (
                conn.execute("SELECT AVG(cost_usd) FROM llm_call_log").fetchone()[0] or 0.0
            )

            queue_depth: int = conn.execute(
                "SELECT COUNT(*) FROM items WHERE status = 'pending_review'"
            ).fetchone()[0]

        return {
            "processed_today": processed_today,
            "success_rate": success_rate,
            "avg_latency_ms": round(avg_latency_ms, 2),
            "avg_cost_usd": round(avg_cost_usd, 6),
            "queue_depth": queue_depth,
        }

    def create_batch_job(self, job_id: str, total: int) -> None:
        """Insert a new batch job record with status=running.

        Args:
            job_id: Unique batch job identifier.
            total: Total number of emails in this batch.
        """
        created = now_utc_iso()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO batch_jobs(job_id, status, total, processed, succeeded, failed_count, created_at, updated_at) VALUES(?,?,?,0,0,0,?,?)",
                (job_id, "running", total, created, created),
            )

    def get_batch_job(self, job_id: str) -> dict[str, Any] | None:
        """Return the batch job row, or None if not found.

        Args:
            job_id: Batch job identifier.

        Returns:
            Row as a dict, or None if not found.
        """
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM batch_jobs WHERE job_id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def increment_batch_result(self, job_id: str, *, succeeded: bool) -> None:
        """Atomically increment processed plus succeeded or failed_count.

        Uses a single SQL UPDATE so concurrent callers cannot interleave a
        read-then-write race condition.

        Args:
            job_id: Batch job to update.
            succeeded: True increments succeeded; False increments failed_count.
        """
        updated = now_utc_iso()
        with self._conn() as conn:
            if succeeded:
                conn.execute(
                    "UPDATE batch_jobs SET processed = processed + 1, succeeded = succeeded + 1, updated_at = ? WHERE job_id = ?",
                    (updated, job_id),
                )
            else:
                conn.execute(
                    "UPDATE batch_jobs SET processed = processed + 1, failed_count = failed_count + 1, updated_at = ? WHERE job_id = ?",
                    (updated, job_id),
                )

    def finalize_batch_job(self, job_id: str) -> None:
        """Mark a batch job as complete.

        Args:
            job_id: Batch job to finalise.
        """
        updated = now_utc_iso()
        with self._conn() as conn:
            conn.execute(
                "UPDATE batch_jobs SET status = 'complete', updated_at = ? WHERE job_id = ?",
                (updated, job_id),
            )

    def list_all_audit_paginated(
        self, page: int, page_size: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a page of audit events across all items with total count.

        Args:
            page: 1-based page number.
            page_size: Number of events per page.

        Returns:
            Tuple of (page rows as dicts, total event count).
        """
        offset = (page - 1) * page_size
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            rows = conn.execute(
                "SELECT id, item_id, event_type, actor, details_json, created_at FROM audit_log ORDER BY id ASC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
            return [dict(r) for r in rows], total
