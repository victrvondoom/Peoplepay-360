"""SQLite persistence for the entities the gateway actually needs.

provider_connections, model_catalog_cache, model_preferences, model_invocations,
conversations. Prompt/response bodies are stored ONLY in ``conversations`` (product
data the user owns); invocation telemetry carries operational metadata, never content.
Credentials are not stored here -- only an opaque ``credential_ref`` into the vault.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .canonical import Conversation, ProviderConnection, ProviderModelRoute


class ModelStore:
    def __init__(self, path: str = ":memory:"):
        self._c = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        with self._lock:
            self._c.executescript("""
            CREATE TABLE IF NOT EXISTS provider_connections (id TEXT PRIMARY KEY, owner_scope TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS model_catalog_cache (connection_id TEXT PRIMARY KEY, refreshed_at REAL NOT NULL, body TEXT NOT NULL, error TEXT);
            CREATE TABLE IF NOT EXISTS model_preferences (owner TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS model_invocations (
                id TEXT PRIMARY KEY, owner TEXT, conversation_id TEXT, connection_id TEXT, provider_id TEXT, model_id TEXT, route TEXT,
                status TEXT, started_at REAL, ended_at REAL, latency_ms REAL, input_tokens INTEGER, output_tokens INTEGER,
                cached_tokens INTEGER, est_cost REAL, fallback_parent TEXT, error_class TEXT, task TEXT, local INTEGER);
            CREATE INDEX IF NOT EXISTS inv_owner ON model_invocations(owner, started_at);
            CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, owner TEXT NOT NULL, updated_at REAL, body TEXT NOT NULL);
            """)

    # connections ---------------------------------------------------------------
    def save_connection(self, c: ProviderConnection) -> None:
        from dataclasses import asdict
        with self._lock:
            self._c.execute("INSERT OR REPLACE INTO provider_connections VALUES (?,?,?)",
                            (c.id, c.owner_scope, json.dumps(asdict(c))))
            self._c.commit()

    def get_connection(self, cid: str) -> ProviderConnection | None:
        with self._lock:
            row = self._c.execute("SELECT body FROM provider_connections WHERE id=?", (cid,)).fetchone()
        return ProviderConnection(**json.loads(row[0])) if row else None

    def list_connections(self, scopes: list[str] | None = None) -> list[ProviderConnection]:
        with self._lock:
            rows = self._c.execute("SELECT body, owner_scope FROM provider_connections ORDER BY rowid").fetchall()
        out = [ProviderConnection(**json.loads(b)) for b, s in rows if scopes is None or s in scopes]
        return out

    def delete_connection(self, cid: str) -> None:
        with self._lock:
            self._c.execute("DELETE FROM provider_connections WHERE id=?", (cid,))
            self._c.execute("DELETE FROM model_catalog_cache WHERE connection_id=?", (cid,))
            self._c.commit()

    # catalog ----------------------------------------------------------------------
    def save_catalog(self, cid: str, routes: list[ProviderModelRoute], error: str | None = None) -> None:
        with self._lock:
            self._c.execute("INSERT OR REPLACE INTO model_catalog_cache VALUES (?,?,?,?)",
                            (cid, time.time(), json.dumps([r.to_dict() for r in routes]), error))
            self._c.commit()

    def get_catalog(self, cid: str) -> tuple[list[ProviderModelRoute], float, str | None] | None:
        with self._lock:
            row = self._c.execute("SELECT body, refreshed_at, error FROM model_catalog_cache WHERE connection_id=?", (cid,)).fetchone()
        if not row:
            return None
        return [ProviderModelRoute.from_dict(d) for d in json.loads(row[0])], row[1], row[2]

    # preferences --------------------------------------------------------------------
    def get_prefs(self, owner: str) -> dict[str, Any]:
        with self._lock:
            row = self._c.execute("SELECT body FROM model_preferences WHERE owner=?", (owner,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_prefs(self, owner: str, prefs: dict[str, Any]) -> None:
        with self._lock:
            self._c.execute("INSERT OR REPLACE INTO model_preferences VALUES (?,?)", (owner, json.dumps(prefs)))
            self._c.commit()

    # invocations ----------------------------------------------------------------------
    def record_invocation(self, rec: dict[str, Any]) -> None:
        cols = ["id", "owner", "conversation_id", "connection_id", "provider_id", "model_id", "route", "status",
                "started_at", "ended_at", "latency_ms", "input_tokens", "output_tokens", "cached_tokens",
                "est_cost", "fallback_parent", "error_class", "task", "local"]
        with self._lock:
            self._c.execute(f"INSERT OR REPLACE INTO model_invocations ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                            [rec.get(c) for c in cols])
            self._c.commit()

    def usage_rows(self, owner: str | None = None, since: float | None = None) -> list[dict]:
        q, args = "SELECT * FROM model_invocations WHERE 1=1", []
        if owner is not None:
            q += " AND owner=?"; args.append(owner)
        if since is not None:
            q += " AND started_at>=?"; args.append(since)
        with self._lock:
            cur = self._c.execute(q, args)
            names = [d[0] for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    # conversations ---------------------------------------------------------------------
    def save_conversation(self, conv: Conversation) -> None:
        with self._lock:
            self._c.execute("INSERT OR REPLACE INTO conversations VALUES (?,?,?,?)",
                            (conv.id, conv.owner, time.time(), json.dumps(conv.to_dict())))
            self._c.commit()

    def get_conversation(self, cid: str, owner: str) -> Conversation | None:
        with self._lock:
            row = self._c.execute("SELECT body FROM conversations WHERE id=? AND owner=?", (cid, owner)).fetchone()
        return Conversation.from_dict(json.loads(row[0])) if row else None

    def list_conversations(self, owner: str) -> list[dict]:
        with self._lock:
            rows = self._c.execute("SELECT id, updated_at, body FROM conversations WHERE owner=? ORDER BY updated_at DESC", (owner,)).fetchall()
        return [{"id": i, "updated_at": u, "title": json.loads(b).get("title", ""), "messages": len(json.loads(b)["messages"])} for i, u, b in rows]
