"""The shared event bus (spec Sec. 26).

Every subsystem emits onto one bus, and every event carries the transaction id
it belongs to.  The bus does not invent event names: the vocabulary is
``beacon.assurance.ledger.EventKind``, which already covers the lifecycle,
authorization, payment, fulfilment, dispute and safety events the spec lists.

Two rules the bus enforces rather than documents:

* An event that names no transaction is refused.  Correlation is the point.
* A subscriber that raises does not stop the publish loop, and its failure is
  itself reported.  A broken listener must not be able to halt a payment path.

The bus is deliberately *not* the source of truth -- the per-transaction
``TransactionLedger`` is.  The bus is how the rest of the system hears about
what the ledger already recorded.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from beacon.assurance.evidence import content_hash, utcnow
from beacon.assurance.ledger import EventKind, LedgerEvent

__all__ = ["Event", "EventBus", "Subscriber"]


@dataclass(frozen=True, slots=True)
class Event:
    """One published event.

    Carries the full set the spec requires: ``transaction_id``, ``event_id``,
    ``timestamp``, ``source``, ``actor`` and ``payload``.
    """

    event_id: str
    transaction_id: str
    kind: EventKind
    timestamp: datetime
    source: str
    """Which subsystem published it: ``spatial``, ``market``, ``payment``..."""

    actor: str
    """Who acted: a user id, an agent name, or a provider id."""

    payload: dict[str, Any] = field(default_factory=dict)
    ledger_seq: int | None = None
    """The ledger sequence this mirrors, when it came from a ledger append."""

    ledger_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "transaction_id": self.transaction_id,
            "kind": str(self.kind),
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "actor": self.actor,
            "payload": self.payload,
            "ledger_seq": self.ledger_seq,
            "ledger_hash": self.ledger_hash,
        }

    @classmethod
    def from_ledger(cls, event: LedgerEvent, *, source: str) -> Event:
        """Mirror a ledger append onto the bus without restating its content."""
        return cls(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            transaction_id=event.transaction_id,
            kind=event.kind,
            timestamp=event.at,
            source=source,
            actor=event.actor,
            payload=dict(event.detail),
            ledger_seq=event.seq,
            ledger_hash=event.event_hash,
        )


Subscriber = Callable[[Event], None]


class EventBus:
    """In-process publish/subscribe with a seam for a real broker.

    Synchronous and ordered on purpose: during a payment path we want the
    subscriber's failure to be visible in the same call stack that published,
    not swallowed by a queue we are not yet operating.  ``drain_to`` is the
    hook for forwarding to SNS/EventBridge/Kafka later without changing callers.
    """

    def __init__(self, *, keep_history: bool = True) -> None:
        self._by_kind: dict[EventKind, list[Subscriber]] = defaultdict(list)
        self._all: list[Subscriber] = []
        self._history: list[Event] = []
        self._keep_history = keep_history
        self._failures: list[dict[str, Any]] = []

    # --- subscription --------------------------------------------------

    def subscribe(self, kind: EventKind, handler: Subscriber) -> None:
        self._by_kind[kind].append(handler)

    def subscribe_all(self, handler: Subscriber) -> None:
        self._all.append(handler)

    # --- publication ---------------------------------------------------

    def publish(
        self,
        kind: EventKind,
        *,
        transaction_id: str,
        source: str,
        actor: str,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> Event:
        if not transaction_id.strip():
            raise ValueError(
                "every event must name its transaction; an uncorrelated event "
                "is not publishable on this bus"
            )
        if not actor.strip():
            raise ValueError("every event must name an actor")
        event = Event(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            transaction_id=transaction_id,
            kind=kind,
            timestamp=timestamp or utcnow(),
            source=source,
            actor=actor,
            payload=dict(payload or {}),
        )
        return self._dispatch(event)

    def publish_ledger_event(self, event: LedgerEvent, *, source: str) -> Event:
        """Mirror one ledger append onto the bus."""
        return self._dispatch(Event.from_ledger(event, source=source))

    def publish_ledger_tail(
        self, ledger: Any, *, source: str, since_seq: int = 0
    ) -> tuple[Event, ...]:
        """Mirror every ledger event after *since_seq*.

        Lets a capability do its work against the aggregate and then announce
        the result in one call, without the aggregate depending on the bus.
        """
        published = [
            self._dispatch(Event.from_ledger(e, source=source))
            for e in ledger.events
            if e.seq > since_seq
        ]
        return tuple(published)

    def _dispatch(self, event: Event) -> Event:
        if self._keep_history:
            self._history.append(event)
        for handler in (*self._by_kind.get(event.kind, ()), *self._all):
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 - a listener must not halt the path
                self._failures.append(
                    {
                        "event_id": event.event_id,
                        "transaction_id": event.transaction_id,
                        "kind": str(event.kind),
                        "handler": getattr(handler, "__name__", repr(handler)),
                        "error": f"{type(exc).__name__}: {exc}",
                        "at": utcnow().isoformat(),
                    }
                )
        return event

    # --- inspection ----------------------------------------------------

    @property
    def history(self) -> tuple[Event, ...]:
        return tuple(self._history)

    @property
    def failures(self) -> tuple[dict[str, Any], ...]:
        """Subscriber failures.  Surfaced, never hidden (spec Sec. 32)."""
        return tuple(self._failures)

    def for_transaction(self, transaction_id: str) -> tuple[Event, ...]:
        return tuple(e for e in self._history if e.transaction_id == transaction_id)

    def of_kind(self, kind: EventKind) -> tuple[Event, ...]:
        return tuple(e for e in self._history if e.kind is kind)

    def fingerprint(self) -> str:
        """Hash of the published sequence, for test assertions and audit."""
        return content_hash([e.to_dict() for e in self._history])

    def drain_to(self, sink: Callable[[dict[str, Any]], None]) -> int:
        """Forward history to an external broker.  Returns the count sent.

        The seam for SNS / EventBridge / Kafka.  Kept explicit so that moving
        to a real broker does not change any publisher.
        """
        for event in self._history:
            sink(event.to_dict())
        return len(self._history)
