"""The canonical Transaction aggregate -- Phase 1.

This is the object the whole system is about.  A room scan, a metro journey, an
exam booking and a laptop purchase are the *same kind of object* with different
context attached -- not four applications that happen to share a database.

The aggregate owns no new machinery.  It composes what ``beacon.assurance``
already provides and was already tested:

    ``State`` / ``assert_transition``   the lifecycle and its legal moves
    ``EvidenceGraph``                   append-only, hashed, provenanced facts
    ``TransactionLedger``               the hash-chained event log
    ``IntentMandate``                   what the user asked for, in their words
    ``Money``                           exact amounts, never floats

What it adds is *identity and coordination*: one ``transaction_id``, one
lifecycle, one event log, and typed optional context slots so that a capability
can attach what it knows without inventing a competing transaction model.

Context slots are deliberately plain dicts rather than per-domain classes.  A
``RumiTransaction`` or ``BookingTransaction`` class is exactly what §2 forbids,
and a dict cannot quietly grow authority the way a class can.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from beacon.assurance import (
    EventKind,
    EvidenceClass,
    EvidenceGraph,
    IntentMandate,
    Money,
    Observation,
    Provenance,
    State,
    TransactionLedger,
    assert_transition,
    utcnow,
)
from beacon.peoplepay.authority import (
    AuthorityError,
    ConditionalGrant,
    Permission,
    PermissionSet,
    TransactionType,
)
from beacon.peoplepay.nodes import PeoplePayNodeKind, SourceType, Visibility

__all__ = ["CONTEXT_SLOTS", "Transaction", "TransactionOwnershipError"]


CONTEXT_SLOTS: tuple[str, ...] = (
    "spatial",
    "market",
    "property",
    "product",
    "booking",
    "payment",
    "fulfillment",
)
"""The optional capability contexts a transaction may carry (§2).

Each is filled by a capability adapter later.  An unfilled slot is absent, not
empty-but-present: "we never looked" and "we looked and found nothing" are
different answers and must stay distinguishable.
"""


class TransactionOwnershipError(RuntimeError):
    """Raised when a user acts on a transaction that is not theirs."""


@dataclass(slots=True)
class Transaction:
    """One transaction, one id, one lifecycle, one log.

    Mutable by design -- it *is* the aggregate root, and its history lives in
    the ledger rather than in copies of itself.  Every mutation that matters
    appends an event, so the object's past is reconstructible from the log.
    """

    transaction_id: str
    user_id: str
    transaction_type: TransactionType
    raw_utterance: str
    """The user's own words, verbatim.  Never overwritten (§7, invariant 2)."""

    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    state: State = State.DRAFT

    language: str | None = None
    """BCP-47-ish tag of the raw utterance, e.g. ``"ta"``.  Detected, not assumed."""

    normalized_intent: str | None = None
    """The system's reading of the utterance.  Derived, never the consent record."""

    mandate: IntentMandate | None = None
    permissions: PermissionSet = field(default_factory=PermissionSet.discovery_only)
    context: dict[str, dict[str, Any]] = field(default_factory=dict)
    plan: dict[str, Any] | None = None
    memory_refs: tuple[str, ...] = ()

    graph: EvidenceGraph = field(init=False)
    ledger: TransactionLedger = field(init=False)

    def __post_init__(self) -> None:
        self.graph = EvidenceGraph(self.transaction_id)
        self.ledger = TransactionLedger(self.transaction_id)

    # --- construction -----------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        raw_utterance: str,
        transaction_type: TransactionType = TransactionType.PURCHASE,
        language: str | None = None,
        actor: str = "peoplepay.agent",
        transaction_id: str | None = None,
    ) -> Transaction:
        """Open a new transaction in ``DRAFT`` and log its creation.

        ``raw_utterance`` is required, because a transaction with no record of
        what the user actually said has no consent basis.
        """
        if not raw_utterance.strip():
            raise ValueError(
                "raw_utterance is required; a transaction needs the user's own "
                "words as its consent record"
            )
        if not user_id.strip():
            raise ValueError("user_id is required; transactions are always owned")

        txn = cls(
            transaction_id=transaction_id or f"txn-{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            transaction_type=transaction_type,
            raw_utterance=raw_utterance,
            language=language,
        )
        txn.ledger.append(
            EventKind.TRANSACTION_CREATED,
            actor=actor,
            detail={
                "transaction_type": str(transaction_type),
                "language": language,
                "utterance_length": len(raw_utterance),
            },
            state_after=State.DRAFT,
        )
        return txn

    # --- ownership --------------------------------------------------------

    def assert_owned_by(self, user_id: str) -> None:
        """Raise unless ``user_id`` owns this transaction (§26)."""
        if user_id != self.user_id:
            raise TransactionOwnershipError(
                f"transaction {self.transaction_id} belongs to another user; "
                "cross-user access is refused"
            )

    # --- lifecycle --------------------------------------------------------

    def transition_to(
        self,
        target: State,
        *,
        actor: str,
        detail: dict[str, Any] | None = None,
    ) -> State:
        """Move to ``target`` if the move is legal, and log it either way.

        Delegates legality to ``beacon.assurance.states.assert_transition`` --
        the table there is the single source of truth.  A refused move is
        recorded, because attempts matter to an audit as much as successes do.
        """
        before = self.state
        try:
            assert_transition(before, target)
        except Exception as exc:
            self.ledger.append(
                EventKind.STATE_CHANGE_REFUSED,
                actor=actor,
                detail={"target": str(target), "reason": str(exc)},
                state_before=before,
            )
            raise
        self.state = target
        self.updated_at = utcnow()
        self.ledger.append(
            EventKind.STATE_CHANGED,
            actor=actor,
            detail=detail or {},
            state_before=before,
            state_after=target,
        )
        return self.state

    # --- intent -----------------------------------------------------------

    def capture_intent(
        self,
        mandate: IntentMandate,
        *,
        normalized_intent: str,
        actor: str = "peoplepay.agent",
    ) -> None:
        """Attach the mandate and the system's reading, and move to INTENT_CAPTURED.

        The mandate must carry the same raw utterance as the transaction: a
        mandate built from a translation would make the translation the consent
        record, which §7 forbids.
        """
        if mandate.raw_utterance != self.raw_utterance:
            raise ValueError(
                "mandate.raw_utterance must match the transaction's raw_utterance; "
                "the consent record cannot be substituted"
            )
        if mandate.user_id != self.user_id:
            raise TransactionOwnershipError(
                "mandate belongs to a different user than the transaction"
            )
        self.mandate = mandate
        self.normalized_intent = normalized_intent
        self.permissions = self.permissions.with_autonomy(mandate.autonomy)

        self.graph.add(
            PeoplePayNodeKind.TRANSACTION_INTENT,  # type: ignore[arg-type]
            actor=actor,
            payload={
                "normalized_intent": normalized_intent,
                "language": self.language,
                "source_type": str(SourceType.SELF_REPORTED),
                "visibility": str(Visibility.PRIVATE),
                "product_query": mandate.product_query,
                "max_amount": (
                    mandate.max_amount.to_dict() if mandate.max_amount else None
                ),
                "currency": mandate.currency,
            },
        )
        self.ledger.append(
            EventKind.INTENT_CAPTURED,
            actor=actor,
            detail={
                "mandate_id": mandate.mandate_id,
                "normalized_intent": normalized_intent,
                "autonomy": str(mandate.autonomy),
                "interpreted_by": mandate.interpreted_by,
            },
        )
        self.transition_to(State.INTENT_CAPTURED, actor=actor)

    # --- context ----------------------------------------------------------

    def attach_context(
        self,
        slot: str,
        payload: dict[str, Any],
        *,
        actor: str,
    ) -> None:
        """Attach capability context to a named slot (§2).

        Unknown slots are refused rather than silently accepted, so a typo does
        not create a phantom capability that nothing reads.
        """
        if slot not in CONTEXT_SLOTS:
            raise ValueError(
                f"unknown context slot {slot!r}; known slots are {CONTEXT_SLOTS}"
            )
        self.context[slot] = payload
        self.updated_at = utcnow()
        self.ledger.append(
            EventKind.EVIDENCE_RECORDED,
            actor=actor,
            detail={"context_slot": slot, "keys": sorted(payload)},
        )

    # --- evidence ---------------------------------------------------------

    def add_evidence(
        self,
        kind: PeoplePayNodeKind,
        *,
        actor: str,
        source: str,
        source_type: SourceType,
        payload: dict[str, Any] | None = None,
        observations: tuple[Observation, ...] = (),
        confidence: float | None = None,
        sandbox: bool = False,
    ) -> str:
        """Record one piece of evidence and return its node id.

        ``source_type`` is stored explicitly (§10) so that a Google review and a
        YouTube video never collapse into an undifferentiated "review".  Sandbox
        provenance is propagated, and ``Observation`` downgrades any
        decision-grade class to ``SANDBOX`` on construction -- invariant 4 is
        enforced by the existing assurance layer, not re-implemented here.
        """
        body = dict(payload or {})
        body["source_type"] = str(source_type)
        body["source"] = source
        if sandbox:
            body["sandbox"] = True

        obs = tuple(observations)
        if (sandbox or source_type is SourceType.SANDBOX) and not any(
            o.provenance.sandbox for o in obs
        ):
            # ``EvidenceNode.is_sandbox`` reads provenance off the *observations*,
            # so a node declared sandbox with none attached would look clean to
            # ``has_sandbox_evidence``.  Record the provenance where the graph
            # actually looks, rather than only in the payload.
            obs = (
                *obs,
                self.observation(
                    field_name="sandbox_marker",
                    value=None,
                    source=source,
                    source_type=source_type,
                    evidence_class=EvidenceClass.SANDBOX,
                    sandbox=True,
                    note="declared sandbox; carries no real-world claim",
                ),
            )

        node = self.graph.add(
            kind,  # type: ignore[arg-type]
            actor=actor,
            payload=body,
            observations=obs,
            confidence=confidence,
        )
        self.updated_at = utcnow()
        self.ledger.append(
            EventKind.EVIDENCE_RECORDED,
            actor=actor,
            detail={
                "node_id": node.node_id,
                "kind": str(kind),
                "source": source,
                "source_type": str(source_type),
                "sandbox": sandbox or node.is_sandbox,
            },
        )
        return node.node_id

    def observation(
        self,
        *,
        field_name: str,
        value: Any,
        source: str,
        source_type: SourceType,
        evidence_class: EvidenceClass = EvidenceClass.UNVERIFIED,
        source_url: str | None = None,
        sandbox: bool = False,
        note: str = "",
    ) -> Observation:
        """Build an ``Observation`` with provenance filled in.

        A convenience over the assurance primitives, not a replacement: the
        returned object is the same ``Observation`` whose ``__post_init__``
        already refuses to attach a value to an ``UNAVAILABLE``/``UNKNOWN``
        class and forces sandbox provenance down to ``SANDBOX``.
        """
        prov = Provenance(
            source=source,
            retrieved_at=utcnow(),
            source_url=source_url,
            adapter=str(source_type),
            sandbox=sandbox,
        )
        return Observation(
            field=field_name,
            value=value,
            provenance=prov,
            evidence_class=evidence_class,
            note=note,
        )

    @property
    def has_sandbox_evidence(self) -> bool:
        """True when any evidence came from a sandbox (§12)."""
        return self.graph.has_sandbox_evidence()

    # --- authority --------------------------------------------------------

    def grant(self, *permissions: Permission, actor: str) -> None:
        """Grant permissions outright and log it."""
        self.permissions = self.permissions.grant(*permissions)
        self.updated_at = utcnow()
        self.ledger.append(
            EventKind.AUTHORIZATION_GRANTED,
            actor=actor,
            detail={"granted": sorted(str(p) for p in permissions)},
        )

    def grant_conditional(self, grant: ConditionalGrant, *, actor: str) -> None:
        """Record a conditional grant such as "buy if under Rs 45,000" (§24)."""
        self.permissions = self.permissions.grant_conditional(grant)
        self.updated_at = utcnow()
        self.ledger.append(
            EventKind.AUTHORIZATION_GRANTED,
            actor=actor,
            detail={"conditional": grant.to_dict()},
        )

    def require_permission(
        self,
        permission: Permission,
        *,
        amount: Money | None = None,
        actor: str = "peoplepay.agent",
    ) -> None:
        """Enforce a permission, logging the denial when it is missing."""
        try:
            self.permissions.require(permission, amount=amount)
        except AuthorityError as exc:
            self.ledger.append(
                EventKind.AUTHORIZATION_REQUESTED,
                actor=actor,
                detail={
                    "permission": str(permission),
                    "amount": amount.to_dict() if amount else None,
                    "outcome": "DENIED",
                    "reason": str(exc),
                },
            )
            raise

    # --- serialization ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe view.  Money stays integer minor units, never a float."""
        return {
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
            "transaction_type": str(self.transaction_type),
            "state": str(self.state),
            "raw_utterance": self.raw_utterance,
            "language": self.language,
            "normalized_intent": self.normalized_intent,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "mandate_id": self.mandate.mandate_id if self.mandate else None,
            "permissions": self.permissions.to_dict(),
            "context": {k: sorted(v) for k, v in self.context.items()},
            "plan": self.plan,
            "memory_refs": list(self.memory_refs),
            "evidence_nodes": len(self.graph),
            "events": len(self.ledger),
            "has_sandbox_evidence": self.has_sandbox_evidence,
        }
