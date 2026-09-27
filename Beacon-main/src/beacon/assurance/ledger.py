"""The append-only transaction ledger and the idempotency guard.

Nothing important happens without an event.  Every state change, every agent
action, every external call that could move money leaves a
:class:`LedgerEvent`, and events are chained by hash so a later reader can
tell whether the history was edited after the fact.

The ledger is deliberately dumb about *meaning* and strict about *order*:

* ``seq`` is monotonic per transaction, assigned here and nowhere else.
* ``prev_hash`` links each event to the one before it, so a removed or
  altered row breaks the chain and :meth:`TransactionLedger.verify_chain`
  says where.
* There is no update and no delete.  A correction is a new event.

:class:`IdempotencyGuard` is the other half of safety: an irreversible action
is claimed under a key before it runs, and a second attempt with the same key
replays the stored result instead of charging twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from beacon.assurance.evidence import content_hash, utcnow

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from beacon.assurance.states import State

__all__ = [
    "EventKind",
    "IdempotencyConflict",
    "IdempotencyGuard",
    "LedgerEvent",
    "TransactionLedger",
]


class EventKind(StrEnum):
    """What happened.  Named for the audit reader, not for the code path."""

    # lifecycle
    TRANSACTION_CREATED = "TRANSACTION_CREATED"
    STATE_CHANGED = "STATE_CHANGED"
    STATE_CHANGE_REFUSED = "STATE_CHANGE_REFUSED"

    # intent and evaluation
    INTENT_CAPTURED = "INTENT_CAPTURED"
    OFFER_DISCOVERED = "OFFER_DISCOVERED"
    EVIDENCE_RECORDED = "EVIDENCE_RECORDED"
    MERCHANT_VERIFIED = "MERCHANT_VERIFIED"
    RISK_EVALUATED = "RISK_EVALUATED"
    POLICY_EVALUATED = "POLICY_EVALUATED"

    # authorization
    CONTRACT_CREATED = "CONTRACT_CREATED"
    AUTHORIZATION_REQUESTED = "AUTHORIZATION_REQUESTED"
    AUTHORIZATION_GRANTED = "AUTHORIZATION_GRANTED"
    AUTHORIZATION_REVOKED = "AUTHORIZATION_REVOKED"
    AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"

    # execution
    CHECKOUT_OBSERVED = "CHECKOUT_OBSERVED"
    CONTRACT_CHECKED = "CONTRACT_CHECKED"
    CONTRACT_VIOLATED = "CONTRACT_VIOLATED"
    CHECKOUT_MANDATE_CREATED = "CHECKOUT_MANDATE_CREATED"
    PAYMENT_MANDATE_CREATED = "PAYMENT_MANDATE_CREATED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_REPLAYED = "PAYMENT_REPLAYED"
    """A duplicate attempt served from the idempotency record, not re-charged."""

    # fulfilment and after
    ORDER_CREATED = "ORDER_CREATED"
    SHIPMENT_CREATED = "SHIPMENT_CREATED"
    DELIVERY_OBSERVED = "DELIVERY_OBSERVED"
    VERIFICATION_RUN = "VERIFICATION_RUN"
    RECONCILIATION_RUN = "RECONCILIATION_RUN"
    SETTLED = "SETTLED"
    REFUND_REQUESTED = "REFUND_REQUESTED"
    REFUND_COMPLETED = "REFUND_COMPLETED"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    RESOLVED = "RESOLVED"

    # agents and safety
    AGENT_ACTION = "AGENT_ACTION"
    AGENT_ACTION_REFUSED = "AGENT_ACTION_REFUSED"
    PROMPT_INJECTION_SUSPECTED = "PROMPT_INJECTION_SUSPECTED"
    KILL_SWITCH_ENGAGED = "KILL_SWITCH_ENGAGED"
    EXCEPTION_RAISED = "EXCEPTION_RAISED"
    HUMAN_INTERVENED = "HUMAN_INTERVENED"


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    """One immutable row.  ``event_hash`` covers the body and ``prev_hash``."""

    seq: int
    transaction_id: str
    kind: EventKind
    at: datetime
    actor: str
    """Who acted: a user id, an agent name, or a provider id.  Never blank."""

    detail: dict[str, Any] = field(default_factory=dict)
    state_before: State | None = None
    state_after: State | None = None
    prev_hash: str = ""
    event_hash: str = ""

    def body(self) -> dict[str, Any]:
        """Exactly what the hash covers."""
        return {
            "seq": self.seq,
            "transaction_id": self.transaction_id,
            "kind": str(self.kind),
            "at": self.at.isoformat(),
            "actor": self.actor,
            "detail": self.detail,
            "state_before": str(self.state_before) if self.state_before else None,
            "state_after": str(self.state_after) if self.state_after else None,
            "prev_hash": self.prev_hash,
        }

    def compute_hash(self) -> str:
        return content_hash(self.body())

    def to_dict(self) -> dict[str, Any]:
        return {**self.body(), "event_hash": self.event_hash}


class TransactionLedger:
    """Append-only, hash-chained event log for one transaction."""

    def __init__(self, transaction_id: str) -> None:
        self.transaction_id = transaction_id
        self._events: list[LedgerEvent] = []

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[LedgerEvent]:
        return iter(self._events)

    @property
    def events(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._events)

    @property
    def head_hash(self) -> str:
        return self._events[-1].event_hash if self._events else ""

    def append(
        self,
        kind: EventKind,
        *,
        actor: str,
        detail: dict[str, Any] | None = None,
        state_before: State | None = None,
        state_after: State | None = None,
        at: datetime | None = None,
    ) -> LedgerEvent:
        """Add one event.  ``seq`` and the hash chain are assigned here."""
        if not actor.strip():
            raise ValueError(
                "every ledger event needs an actor; anonymous writes are not allowed"
            )
        draft = LedgerEvent(
            seq=len(self._events) + 1,
            transaction_id=self.transaction_id,
            kind=kind,
            at=at or utcnow(),
            actor=actor,
            detail=dict(detail or {}),
            state_before=state_before,
            state_after=state_after,
            prev_hash=self.head_hash,
        )
        sealed = LedgerEvent(
            seq=draft.seq,
            transaction_id=draft.transaction_id,
            kind=draft.kind,
            at=draft.at,
            actor=draft.actor,
            detail=draft.detail,
            state_before=draft.state_before,
            state_after=draft.state_after,
            prev_hash=draft.prev_hash,
            event_hash=draft.compute_hash(),
        )
        self._events.append(sealed)
        return sealed

    def of_kind(self, kind: EventKind) -> tuple[LedgerEvent, ...]:
        return tuple(e for e in self._events if e.kind == kind)

    def last(self, kind: EventKind) -> LedgerEvent | None:
        for event in reversed(self._events):
            if event.kind == kind:
                return event
        return None

    def count(self, kind: EventKind) -> int:
        return sum(1 for e in self._events if e.kind == kind)

    def verify_chain(self) -> tuple[bool, str]:
        """Re-walk the chain.  Returns ``(ok, message)``.

        This is what makes the log evidence rather than a narrative: if a row
        was altered or removed after the fact, the recomputed hash no longer
        matches and the sequence number of the break is named.
        """
        previous = ""
        for index, event in enumerate(self._events, start=1):
            if event.seq != index:
                return False, f"sequence gap at position {index}: seq={event.seq}"
            if event.prev_hash != previous:
                return False, f"broken link at seq={event.seq}"
            if event.event_hash != event.compute_hash():
                return False, f"tampered content at seq={event.seq}"
            previous = event.event_hash
        return True, f"chain intact across {len(self._events)} events"

    def timeline(self) -> list[dict[str, Any]]:
        """Human-readable history, for the transaction detail page."""
        return [
            {
                "seq": e.seq,
                "at": e.at.isoformat(),
                "kind": str(e.kind),
                "actor": e.actor,
                "state": str(e.state_after) if e.state_after else None,
                "detail": e.detail,
            }
            for e in self._events
        ]

    def to_dict(self) -> dict[str, Any]:
        ok, message = self.verify_chain()
        return {
            "transaction_id": self.transaction_id,
            "events": [e.to_dict() for e in self._events],
            "head_hash": self.head_hash,
            "chain_ok": ok,
            "chain_message": message,
        }


class IdempotencyConflict(RuntimeError):
    """Raised when a key is reused for a materially different operation.

    Reusing one key for two different payments is a bug that would otherwise
    silently suppress the second charge, so it fails loudly instead.
    """


@dataclass(frozen=True, slots=True)
class Claim:
    """A reserved idempotency key, with the result once the action completed."""

    key: str
    fingerprint: str
    claimed_at: datetime
    result: dict[str, Any] | None = None
    completed_at: datetime | None = None

    @property
    def is_complete(self) -> bool:
        return self.result is not None


class IdempotencyGuard:
    """Claim-then-run protection for irreversible operations.

    Usage is two-phase on purpose.  ``claim`` records the intent *before* the
    external call, so a crash between claim and completion leaves a visible
    in-flight record rather than an invisible maybe-charge::

        claim = guard.claim("pay-tx1", {"amount_minor": 10999900})
        if claim.is_complete:
            return claim.result          # already done; replay it
        result = provider.capture(...)   # the irreversible bit
        guard.complete("pay-tx1", result)
    """

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}

    def claim(self, key: str, operation: dict[str, Any]) -> Claim:
        """Reserve *key*.  Returns the existing claim if there is one."""
        if not key:
            raise ValueError("an idempotency key is required for irreversible actions")
        fingerprint = content_hash(operation)
        existing = self._claims.get(key)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise IdempotencyConflict(
                    f"key {key!r} was already used for a different operation; "
                    "refusing to treat these as the same action"
                )
            return existing
        claim = Claim(key=key, fingerprint=fingerprint, claimed_at=utcnow())
        self._claims[key] = claim
        return claim

    def complete(self, key: str, result: dict[str, Any]) -> Claim:
        """Attach the outcome so later attempts replay rather than re-run."""
        claim = self._claims.get(key)
        if claim is None:
            raise KeyError(f"no claim for {key!r}; complete() must follow claim()")
        if claim.is_complete:
            return claim
        done = Claim(
            key=claim.key,
            fingerprint=claim.fingerprint,
            claimed_at=claim.claimed_at,
            result=dict(result),
            completed_at=utcnow(),
        )
        self._claims[key] = done
        return done

    def result_for(self, key: str) -> dict[str, Any] | None:
        claim = self._claims.get(key)
        return claim.result if claim else None

    def in_flight(self) -> tuple[str, ...]:
        """Keys claimed but never completed -- the ones a human should look at."""
        return tuple(k for k, c in self._claims.items() if not c.is_complete)
