"""Central transaction state (spec Sec. 38).

What lives here: transactions, their events, contracts, authorizations and
evidence -- the things that must have exactly one home.

What deliberately does *not* live here: Rumi's spatial data, InflationForge's
observations, InHeir's property documents, PROXY's case graph.  Those systems
keep their own stores; we hold a correlation reference
(``Transaction.subsystem_refs``) and nothing more.  The spec is explicit that
we do not migrate working systems into one database.

``InMemoryTransactionStore`` is the reference implementation and is what the
tests and the local gateway use.  ``TransactionStore`` is the protocol a
DynamoDB / Postgres backend implements later without touching callers.

The aggregate itself is ``beacon.peoplepay.transaction.Transaction`` -- the
canonical one.  This module stores it; it does not define a second one.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from beacon.assurance.states import OPEN_STATES, State

from beacon.peoplepay.transaction import Transaction

__all__ = [
    "InMemoryTransactionStore",
    "JsonSnapshotStore",
    "TransactionNotFound",
    "TransactionStore",
]


class TransactionNotFound(KeyError):
    def __init__(self, transaction_id: str) -> None:
        self.transaction_id = transaction_id
        super().__init__(f"no transaction {transaction_id!r}")


@runtime_checkable
class TransactionStore(Protocol):
    """The seam a real backend implements."""

    def put(self, tx: Transaction) -> None: ...

    def get(self, transaction_id: str) -> Transaction: ...

    def exists(self, transaction_id: str) -> bool: ...

    def for_user(self, user_id: str) -> tuple[Transaction, ...]: ...

    def open_transactions(self) -> tuple[Transaction, ...]: ...


class InMemoryTransactionStore:
    """Process-local store.  Thread-safe because the gateway serves concurrently.

    Holds the live aggregate rather than a serialized copy: the ledger's hash
    chain is verifiable only on the real object, and round-tripping through
    JSON would quietly become a second source of truth.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, Transaction] = {}
        self._lock = threading.RLock()

    def put(self, tx: Transaction) -> None:
        with self._lock:
            existing = self._by_id.get(tx.transaction_id)
            if existing is not None and existing is not tx:
                raise ValueError(
                    f"transaction {tx.transaction_id} is already stored as a "
                    "different object; there is one aggregate per id"
                )
            self._by_id[tx.transaction_id] = tx

    def get(self, transaction_id: str) -> Transaction:
        with self._lock:
            try:
                return self._by_id[transaction_id]
            except KeyError:
                raise TransactionNotFound(transaction_id) from None

    def exists(self, transaction_id: str) -> bool:
        with self._lock:
            return transaction_id in self._by_id

    def for_user(self, user_id: str) -> tuple[Transaction, ...]:
        with self._lock:
            return tuple(t for t in self._by_id.values() if t.user_id == user_id)

    def open_transactions(self) -> tuple[Transaction, ...]:
        with self._lock:
            return tuple(t for t in self._by_id.values() if t.state in OPEN_STATES)

    def in_state(self, state: State) -> tuple[Transaction, ...]:
        with self._lock:
            return tuple(t for t in self._by_id.values() if t.state is state)

    def all(self) -> tuple[Transaction, ...]:
        with self._lock:
            return tuple(self._by_id.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_id)

    # --- integrity -----------------------------------------------------

    def verify_all(self) -> dict[str, str]:
        """Re-verify every ledger chain.  Maps id -> failure message.

        Empty result means every transaction's audit log is intact.
        """
        broken: dict[str, str] = {}
        for tx in self.all():
            # The canonical aggregate exposes the chain on its ledger; there is
            # no verify_integrity() shortcut on the transaction itself.
            ok, message = tx.ledger.verify_chain()
            if not ok:
                broken[tx.transaction_id] = message
        return broken


class JsonSnapshotStore:
    """Writes read-only snapshots beside the live store.

    For inspection, dispute packages and demos -- never read back as the source
    of truth, because a snapshot cannot carry a verifiable hash chain that was
    computed in memory.  ``Transaction.to_dict`` is the shape on disk.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def write(self, tx: Transaction) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{tx.transaction_id}.json"
        payload: dict[str, Any] = tx.to_dict()
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return path

    def read_raw(self, transaction_id: str) -> dict[str, Any]:
        """Read a snapshot back as plain data, clearly not as an aggregate."""
        path = self.directory / f"{transaction_id}.json"
        if not path.exists():
            raise TransactionNotFound(transaction_id)
        return json.loads(path.read_text(encoding="utf-8"))
