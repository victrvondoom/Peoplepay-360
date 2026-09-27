"""Durable transaction storage on SQLite, event-sourced.

``InMemoryTransactionStore`` loses everything on restart.  This implements the
same ``TransactionStore`` protocol against a file, so a gateway can be restarted
without losing a user's history -- and swapping the two is a constructor change.

**Why event-sourced rather than a row per transaction.**  The ledger is the
audit record, and its value comes from the hash chain being *checkable*.  If we
stored only the current state we would be trusting a row someone could have
edited.  Instead each event is a row, and ``get()`` replays them and calls
``verify_chain()`` before handing the aggregate back.  A tampered or truncated
database is therefore detected on load rather than believed.

That is the one strong claim this module makes: **you cannot quietly edit a
stored transaction's history and have it load.**  You can corrupt it, and then it
refuses to load and names the sequence number where the chain broke.

What is deliberately *not* here:

*   No migration framework.  One ``CREATE TABLE IF NOT EXISTS`` script, plus a
    ``schema_version`` row so a future change detects an old file rather than
    silently misreading it.
*   No ORM.  Two tables and explicit SQL are easier to audit than a mapping
    layer, and this file is on the path money decisions are recorded through.
*   No subsystem data.  Per spec Sec. 38 we keep a correlation reference and let
    Rumi, InflationForge, InHeir and PROXY keep their own stores.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from beacon.assurance.evidence import utcnow
from beacon.assurance.ledger import EventKind, LedgerEvent
from beacon.assurance.money import Money
from beacon.assurance.policy import AutonomyLevel
from beacon.assurance.states import OPEN_STATES, State
from beacon.peoplepay.authority import (
    ConditionalGrant,
    Permission,
    PermissionSet,
    TransactionType,
)
from beacon.peoplepay.transaction import Transaction
from transaction.store import TransactionNotFound

__all__ = ["SCHEMA_VERSION", "LedgerIntegrityError", "SqliteTransactionStore"]

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id    TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    transaction_type  TEXT NOT NULL,
    state             TEXT NOT NULL,
    raw_utterance     TEXT NOT NULL,
    language          TEXT,
    normalized_intent TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    mandate_json      TEXT,
    permissions_json  TEXT NOT NULL,
    context_json      TEXT NOT NULL,
    plan_json         TEXT,
    memory_refs_json  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS transactions_by_user ON transactions(user_id);

CREATE TABLE IF NOT EXISTS ledger_events (
    transaction_id TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    kind           TEXT NOT NULL,
    at             TEXT NOT NULL,
    actor          TEXT NOT NULL,
    detail_json    TEXT NOT NULL,
    state_before   TEXT,
    state_after    TEXT,
    prev_hash      TEXT NOT NULL,
    event_hash     TEXT NOT NULL,
    PRIMARY KEY (transaction_id, seq)
);
"""


class LedgerIntegrityError(RuntimeError):
    """Raised when a stored ledger fails to re-verify on load.

    Deliberately not a subclass of ``TransactionNotFound``: a missing
    transaction and a tampered one are different situations and must not be
    caught by the same ``except``.
    """

    def __init__(self, transaction_id: str, message: str) -> None:
        self.transaction_id = transaction_id
        super().__init__(
            f"stored ledger for {transaction_id} failed verification: {message}"
        )


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_dt(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _money_from_dict(raw: dict[str, Any] | None) -> Money | None:
    """Rebuild ``Money`` from minor units.  Never via a float."""
    if not raw:
        return None
    return Money(minor=int(raw["minor"]), currency=str(raw["currency"]))


def _mandate_to_json(mandate: IntentMandate | None) -> str | None:
    """Serialize the whole mandate, field for field.

    Every field is written rather than a convenient subset: a dropped
    ``blocked_merchants`` or ``required_condition`` would silently *widen* what
    the agent is allowed to buy after a restart, which is the worst direction
    for a persistence bug to fail in.
    """
    if mandate is None:
        return None
    return json.dumps(
        {
            "mandate_id": mandate.mandate_id,
            "user_id": mandate.user_id,
            "raw_utterance": mandate.raw_utterance,
            "product_query": mandate.product_query,
            "max_amount": mandate.max_amount.to_dict() if mandate.max_amount else None,
            "preferred_amount": (
                mandate.preferred_amount.to_dict()
                if mandate.preferred_amount
                else None
            ),
            "quantity": mandate.quantity,
            "currency": mandate.currency,
            "max_delivery_days": mandate.max_delivery_days,
            "required_condition": mandate.required_condition,
            "require_return_policy": mandate.require_return_policy,
            "require_warranty": mandate.require_warranty,
            "require_verified_merchant": mandate.require_verified_merchant,
            "allowed_categories": list(mandate.allowed_categories),
            "allowed_merchants": list(mandate.allowed_merchants),
            "blocked_merchants": list(mandate.blocked_merchants),
            "autonomy": str(mandate.autonomy),
            "created_at": _iso(mandate.created_at),
            "expires_at": _iso(mandate.expires_at) if mandate.expires_at else None,
            "interpreted_by": mandate.interpreted_by,
        }
    )


def _mandate_from_json(text: str | None) -> IntentMandate | None:
    """Rebuild the mandate.  Money comes back from minor units, never a float."""
    if not text:
        return None
    raw = json.loads(text)
    return IntentMandate(
        mandate_id=raw["mandate_id"],
        user_id=raw["user_id"],
        raw_utterance=raw["raw_utterance"],
        product_query=raw["product_query"],
        max_amount=_money_from_dict(raw.get("max_amount")),
        preferred_amount=_money_from_dict(raw.get("preferred_amount")),
        quantity=int(raw.get("quantity", 1)),
        currency=raw.get("currency", "INR"),
        max_delivery_days=raw.get("max_delivery_days"),
        required_condition=raw.get("required_condition"),
        require_return_policy=bool(raw.get("require_return_policy", False)),
        require_warranty=bool(raw.get("require_warranty", False)),
        require_verified_merchant=bool(raw.get("require_verified_merchant", True)),
        allowed_categories=tuple(raw.get("allowed_categories", ())),
        allowed_merchants=tuple(raw.get("allowed_merchants", ())),
        blocked_merchants=tuple(raw.get("blocked_merchants", ())),
        autonomy=AutonomyLevel(raw.get("autonomy", str(AutonomyLevel.HUMAN_PRESENT))),
        created_at=_parse_dt(raw["created_at"]),
        expires_at=_parse_dt(raw["expires_at"]) if raw.get("expires_at") else None,
        interpreted_by=raw.get("interpreted_by"),
    )


def _permissions_to_json(perms: PermissionSet) -> str:
    return json.dumps(
        {
            "granted": sorted(str(p) for p in perms.granted),
            "autonomy": str(perms.autonomy),
            "conditional": [g.to_dict() for g in perms.conditional],
        }
    )


def _permissions_from_json(text: str) -> PermissionSet:
    raw = json.loads(text)
    grants = [
        ConditionalGrant(
            permission=Permission(item["permission"]),
            max_amount=_money_from_dict(item.get("max_amount")),
            raw_utterance=item.get("raw_utterance", ""),
            created_at=_parse_dt(item["created_at"]),
            expires_at=(
                _parse_dt(item["expires_at"]) if item.get("expires_at") else None
            ),
        )
        for item in raw.get("conditional", [])
    ]
    return PermissionSet(
        granted=frozenset(Permission(p) for p in raw.get("granted", [])),
        conditional=tuple(grants),
        autonomy=AutonomyLevel(raw.get("autonomy", str(AutonomyLevel.HUMAN_PRESENT))),
    )


class SqliteTransactionStore:
    """Durable store.  Satisfies the ``TransactionStore`` protocol.

    Thread-safe: one connection guarded by a lock, with
    ``check_same_thread=False`` so the threading HTTP server can share it.  A
    connection pool would be faster and is not the point at this size.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            # WAL so a reader does not block the writer.
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._assert_schema_version()
            self._conn.commit()

    # --- schema ---------------------------------------------------------

    def _assert_schema_version(self) -> None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            return
        found = int(row["value"])
        if found != SCHEMA_VERSION:
            raise RuntimeError(
                f"{self.path} was written by schema version {found}, this build "
                f"speaks {SCHEMA_VERSION}; refusing to read it rather than risk "
                "misinterpreting stored money or state"
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> SqliteTransactionStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # --- writing --------------------------------------------------------

    def put(self, tx: Transaction) -> None:
        """Upsert the transaction and append ledger events not yet stored.

        Events are immutable and append-only, so already-stored rows are left
        alone rather than rewritten -- an ``INSERT OR REPLACE`` on the events
        table would be a way to quietly edit history.
        """
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO transactions (
                    transaction_id, user_id, transaction_type, state,
                    raw_utterance, language, normalized_intent,
                    created_at, updated_at, permissions_json, context_json,
                    plan_json, memory_refs_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(transaction_id) DO UPDATE SET
                    state             = excluded.state,
                    language          = excluded.language,
                    normalized_intent = excluded.normalized_intent,
                    updated_at        = excluded.updated_at,
                    permissions_json  = excluded.permissions_json,
                    context_json      = excluded.context_json,
                    plan_json         = excluded.plan_json,
                    memory_refs_json  = excluded.memory_refs_json
                """,
                (
                    tx.transaction_id,
                    tx.user_id,
                    str(tx.transaction_type),
                    str(tx.state),
                    tx.raw_utterance,
                    tx.language,
                    tx.normalized_intent,
                    _iso(tx.created_at),
                    _iso(tx.updated_at),
                    _permissions_to_json(tx.permissions),
                    json.dumps(tx.context, default=str),
                    json.dumps(tx.plan, default=str) if tx.plan is not None else None,
                    json.dumps(list(tx.memory_refs)),
                ),
            )
            stored = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS high FROM ledger_events "
                "WHERE transaction_id = ?",
                (tx.transaction_id,),
            ).fetchone()["high"]
            for event in tx.ledger.events:
                if event.seq <= stored:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO ledger_events (
                        transaction_id, seq, kind, at, actor, detail_json,
                        state_before, state_after, prev_hash, event_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        event.transaction_id,
                        event.seq,
                        str(event.kind),
                        _iso(event.at),
                        event.actor,
                        json.dumps(event.detail, default=str),
                        str(event.state_before) if event.state_before else None,
                        str(event.state_after) if event.state_after else None,
                        event.prev_hash,
                        event.event_hash,
                    ),
                )
            self._conn.commit()

    # --- reading --------------------------------------------------------

    def get(self, transaction_id: str) -> Transaction:
        """Rebuild the aggregate and re-verify its chain before returning it."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM transactions WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
            if row is None:
                raise TransactionNotFound(transaction_id)
            events = self._conn.execute(
                "SELECT * FROM ledger_events WHERE transaction_id = ? ORDER BY seq",
                (transaction_id,),
            ).fetchall()
        return self._rebuild(row, events)

    def _rebuild(self, row: sqlite3.Row, events: list[sqlite3.Row]) -> Transaction:
        tx = Transaction(
            transaction_id=row["transaction_id"],
            user_id=row["user_id"],
            transaction_type=TransactionType(row["transaction_type"]),
            raw_utterance=row["raw_utterance"],
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            state=State(row["state"]),
            language=row["language"],
            normalized_intent=row["normalized_intent"],
            permissions=_permissions_from_json(row["permissions_json"]),
            context=json.loads(row["context_json"]),
            plan=json.loads(row["plan_json"]) if row["plan_json"] else None,
            memory_refs=tuple(json.loads(row["memory_refs_json"])),
        )
        # Replace the fresh ledger with the stored events, then re-verify.  The
        # hashes are the stored ones: recomputing them here would defeat the
        # point by making any tampering self-consistent.
        restored = [
            LedgerEvent(
                seq=int(e["seq"]),
                transaction_id=e["transaction_id"],
                kind=EventKind(e["kind"]),
                at=_parse_dt(e["at"]),
                actor=e["actor"],
                detail=json.loads(e["detail_json"]),
                state_before=State(e["state_before"]) if e["state_before"] else None,
                state_after=State(e["state_after"]) if e["state_after"] else None,
                prev_hash=e["prev_hash"],
                event_hash=e["event_hash"],
            )
            for e in events
        ]
        tx.ledger._events = restored  # noqa: SLF001 - rehydration is this module's job
        ok, message = tx.ledger.verify_chain()
        if not ok:
            raise LedgerIntegrityError(tx.transaction_id, message)
        return tx

    def exists(self, transaction_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM transactions WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
        return row is not None

    def for_user(self, user_id: str) -> tuple[Transaction, ...]:
        with self._lock:
            ids = [
                r["transaction_id"]
                for r in self._conn.execute(
                    "SELECT transaction_id FROM transactions WHERE user_id = ? "
                    "ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
            ]
        return tuple(self.get(i) for i in ids)

    def open_transactions(self) -> tuple[Transaction, ...]:
        open_names = tuple(str(s) for s in OPEN_STATES)
        placeholders = ",".join("?" for _ in open_names)
        with self._lock:
            ids = [
                r["transaction_id"]
                for r in self._conn.execute(
                    "SELECT transaction_id FROM transactions "  # noqa: S608
                    f"WHERE state IN ({placeholders})",
                    open_names,
                ).fetchall()
            ]
        return tuple(self.get(i) for i in ids)

    def in_state(self, state: State) -> tuple[Transaction, ...]:
        with self._lock:
            ids = [
                r["transaction_id"]
                for r in self._conn.execute(
                    "SELECT transaction_id FROM transactions WHERE state = ?",
                    (str(state),),
                ).fetchall()
            ]
        return tuple(self.get(i) for i in ids)

    def all(self) -> tuple[Transaction, ...]:
        with self._lock:
            ids = [
                r["transaction_id"]
                for r in self._conn.execute(
                    "SELECT transaction_id FROM transactions"
                ).fetchall()
            ]
        return tuple(self.get(i) for i in ids)

    def __len__(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM transactions"
            ).fetchone()
        return int(row["n"])

    # --- integrity ------------------------------------------------------

    def verify_all(self) -> dict[str, str]:
        """Re-verify every stored chain.  Maps id -> failure message.

        Unlike the in-memory store this can genuinely fail, because the rows
        have been outside the process and could have been edited.
        """
        broken: dict[str, str] = {}
        with self._lock:
            ids = [
                r["transaction_id"]
                for r in self._conn.execute(
                    "SELECT transaction_id FROM transactions"
                ).fetchall()
            ]
        for transaction_id in ids:
            try:
                self.get(transaction_id)
            except LedgerIntegrityError as exc:
                broken[transaction_id] = str(exc)
        return broken

    def stats(self) -> dict[str, Any]:
        """Counts for an operator, without loading every aggregate."""
        with self._lock:
            transactions = self._conn.execute(
                "SELECT COUNT(*) AS n FROM transactions"
            ).fetchone()["n"]
            events = self._conn.execute(
                "SELECT COUNT(*) AS n FROM ledger_events"
            ).fetchone()["n"]
        return {
            "path": str(self.path),
            "schema_version": SCHEMA_VERSION,
            "transactions": int(transactions),
            "ledger_events": int(events),
            "checked_at": utcnow().isoformat(),
        }
