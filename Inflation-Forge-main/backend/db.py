from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from backend.utils import jsonable


SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  kind TEXT NOT NULL,
  id TEXT NOT NULL,
  parent_id TEXT,
  created_at TEXT NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (kind, id)
);
CREATE INDEX IF NOT EXISTS idx_records_kind_created ON records(kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_records_parent ON records(kind, parent_id);
CREATE TABLE IF NOT EXISTS state (
  key TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def put(self, kind: str, record_id: str, value: Any, parent_id: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(jsonable(value), sort_keys=True, default=str)
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO records(kind,id,parent_id,created_at,payload) VALUES(?,?,?,?,?)",
                (kind, record_id, parent_id, now, payload),
            )

    def get(self, kind: str, record_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM records WHERE kind=? AND id=?", (kind, record_id)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, kind: str, parent_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT payload FROM records WHERE kind=?"
        parameters: list[Any] = [kind]
        if parent_id is not None:
            query += " AND parent_id=?"
            parameters.append(parent_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def set_state(self, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(jsonable(value), sort_keys=True, default=str)
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO state(key,payload,updated_at) VALUES(?,?,?)",
                (key, payload, now),
            )

    def get_state(self, key: str) -> Any | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row["payload"]) if row else None

