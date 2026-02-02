import json
import os
import sqlite3
from typing import Any, Optional
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_items_message_id ON items(message_id);
CREATE INDEX IF NOT EXISTS idx_audit_item_id ON audit_log(item_id);
"""

class Storage:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def get_by_message_id(self, message_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE message_id = ?", (message_id,)).fetchone()
            return dict(row) if row else None

    def get_item(self, item_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
            return dict(row) if row else None

    def list_items(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if status:
                rows = conn.execute("SELECT * FROM items WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM items ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def create_item(self, item_id: str, message_id: str, status: str, confidence: float, extraction: dict) -> None:
        created = now_utc_iso()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO items(item_id, message_id, status, confidence, extraction_json, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (item_id, message_id, status, confidence, json.dumps(extraction), created, created),
            )

    def update_status(self, item_id: str, status: str) -> None:
        updated = now_utc_iso()
        with self._conn() as conn:
            conn.execute("UPDATE items SET status = ?, updated_at = ? WHERE item_id = ?", (status, updated, item_id))

    def write_audit(self, item_id: str, event_type: str, actor: str, details: dict) -> None:
        created = now_utc_iso()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO audit_log(item_id, event_type, actor, details_json, created_at) VALUES(?,?,?,?,?)",
                (item_id, event_type, actor, json.dumps(details), created),
            )

    def list_audit(self, item_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, item_id, event_type, actor, details_json, created_at FROM audit_log WHERE item_id = ? ORDER BY id ASC",
                (item_id,),
            ).fetchall()
            return [dict(r) for r in rows]
