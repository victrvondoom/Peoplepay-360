"""Gateway-owned durable journey progress; canonical decisions are held by ECHO."""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class JourneyStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS peoplepay_journeys (id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self.connection.commit()

    def put(self, record: dict[str, Any]) -> None:
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                old = self.connection.execute("SELECT owner,payload FROM peoplepay_journeys WHERE id=?", (record["id"],)).fetchone()
                if old and old[0] != record["actor_id"]:
                    raise ValueError("journey owner cannot change")
                revision = json.loads(old[1]).get("_revision", 0) if old else 0
                if record.get("_revision", 0) != revision:
                    raise ValueError("journey progress changed concurrently; reload before retrying")
                updated = {**record, "_revision": revision + 1}
                self.connection.execute(
                    "INSERT INTO peoplepay_journeys(id,owner,payload) VALUES(?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                    (record["id"], record["actor_id"], json.dumps(updated, allow_nan=False)),
                )
                self.connection.commit()
                record["_revision"] = revision + 1
            except Exception:
                self.connection.rollback()
                raise

    def get(self, journey_id: str, actor_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.connection.execute("SELECT payload FROM peoplepay_journeys WHERE id=? AND owner=?",
                                          (journey_id, actor_id)).fetchone()
        if not row:
            raise KeyError("journey not found")
        return json.loads(row[0])

    def list(self, actor_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.connection.execute("SELECT payload FROM peoplepay_journeys WHERE owner=? ORDER BY rowid DESC LIMIT 50",
                                           (actor_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]
