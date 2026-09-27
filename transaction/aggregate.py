"""The one transaction object every capability contributes to.

``beacon.assurance`` already provides every *part* of this: the lifecycle
(``states``), the evidence graph, the contract and drift check, the mandate
chain, the hash-chained ledger and the idempotency guard.  What it did not
provide is the aggregate that binds them to a single id -- so that is all this
module is.  It composes; it re-implements nothing.

The rule inherited from ``assurance`` and kept here: an LLM may propose, this
object records and refuses.  Every state move goes through
``states.assert_transition``, and every move is written to the ledger *after*
the check passes -- so a refused move is auditable too.

One transaction id.  Every subsystem correlates to it (spec Sec. 5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from beacon.assurance.contract import (
    Authorization,
    CheckoutMandate,
    ContractViolation,
    ObservedCheckout,
    PaymentMandate,
    TransactionContract,
)
from beacon.assurance.evidence import (
    EdgeKind,
    EvidenceClass,
    EvidenceGraph,
    EvidenceNode,
    NodeKind,
    Observation,
    utcnow,
)
from beacon.assurance.ledger import (
    EventKind,
    IdempotencyGuard,
    LedgerEvent,
    TransactionLedger,
)
from beacon.assurance.money import Money
from beacon.assurance.policy import Decision, IntentMandate, Policy
from beacon.assurance.states import (
    IRREVERSIBLE_AFTER,
    TERMINAL_STATES,
    IllegalTransition,
    State,
    assert_transition,
    is_open,
)

__all__ = [
    "Transaction",
    "TransactionType",
    "new_transaction_id",
]


def new_transaction_id() -> str:
    return f"tx-{uuid.uuid4().hex[:12]}"


class TransactionType:
    """What kind of real-world transaction this is.

    A plain namespace rather than an enum member per vertical: a booking is
    not a different architecture, it is the same lifecycle with a different
    type tag (spec Sec. 20).
    """

    PURCHASE = "PURCHASE"
    BOOKING = "BOOKING"
    PROPERTY = "PROPERTY"
    BASKET = "BASKET"
    PAYMENT = "PAYMENT"


@dataclass
class Transaction:
    """One real-world transaction, from intent to settlement or resolution.

    Mutable by design -- it is the live aggregate.  Everything *inside* it
    (ledger events, evidence nodes, contracts, authorizations) is immutable and
    append-only, so history cannot be rewritten through this handle.
    """

    transaction_id: str
    user_id: str
    transaction_type: str = TransactionType.PURCHASE
    state: State = State.DRAFT
    created_at: datetime = field(default_factory=utcnow)

    # --- the assurance primitives, one instance each ---------------------
    ledger: TransactionLedger = field(init=False)
    evidence: EvidenceGraph = field(init=False)
    idempotency: IdempotencyGuard = field(init=False, default_factory=IdempotencyGuard)

    # --- what the capabilities contribute -------------------------------
    mandate: IntentMandate | None = None
    policy: Policy | None = None
    contract: TransactionContract | None = None
    authorization: Authorization | None = None
    checkout_mandate: CheckoutMandate | None = None
    payment_mandate: PaymentMandate | None = None

    # Correlation ids into the subsystems that own their own data (Sec. 38).
    # We hold references, never copies of their state.
    subsystem_refs: dict[str, str] = field(default_factory=dict)

    # Open exceptions, newest last.  Cleared only by an explicit resolution.
    exceptions: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ledger = TransactionLedger(self.transaction_id)
        self.evidence = EvidenceGraph(self.transaction_id)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    @classmethod
    def open(
        cls,
        *,
        user_id: str,
        actor: str,
        transaction_type: str = TransactionType.PURCHASE,
        transaction_id: str | None = None,
    ) -> Transaction:
        """Create a transaction in ``DRAFT`` and record its first event."""
        if not user_id.strip():
            raise ValueError("a transaction must belong to a user")
        tx = cls(
            transaction_id=transaction_id or new_transaction_id(),
            user_id=user_id,
            transaction_type=transaction_type,
        )
        tx.ledger.append(
            EventKind.TRANSACTION_CREATED,
            actor=actor,
            detail={"transaction_type": transaction_type, "user_id": user_id},
            state_after=State.DRAFT,
        )
        return tx

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return is_open(self.state)

    @property
    def is_cancellable(self) -> bool:
        """False once money has moved: recovery is a refund, never a rewind."""
        return (
            self.state not in IRREVERSIBLE_AFTER and self.state not in TERMINAL_STATES
        )

    def move_to(
        self,
        target: State,
        *,
        actor: str,
        detail: dict[str, Any] | None = None,
    ) -> LedgerEvent:
        """Move state, or refuse and record the refusal.

        The check is ``assert_transition`` -- plain Python, no model in the
        call path.  A refusal is itself a ledger event, so an agent cannot
        quietly retry its way around the lifecycle.
        """
        before = self.state
        try:
            assert_transition(before, target)
        except IllegalTransition as exc:
            self.ledger.append(
                EventKind.STATE_CHANGE_REFUSED,
                actor=actor,
                detail={**(detail or {}), "attempted": str(target), "reason": str(exc)},
                state_before=before,
            )
            raise
        self.state = target
        return self.ledger.append(
            EventKind.STATE_CHANGED,
            actor=actor,
            detail=dict(detail or {}),
            state_before=before,
            state_after=target,
        )

    # ------------------------------------------------------------------
    # intent
    # ------------------------------------------------------------------

    def capture_intent(
        self,
        mandate: IntentMandate,
        policy: Policy,
        *,
        actor: str,
    ) -> EvidenceNode:
        """Attach the user's mandate and the policy it will be judged against.

        ``mandate.interpreted_by`` may name the model that proposed this
        reading; that field grants no authority and is recorded for audit only.
        """
        if mandate.user_id != self.user_id:
            raise ValueError(
                f"mandate belongs to {mandate.user_id!r}, "
                f"transaction to {self.user_id!r}"
            )
        self.mandate = mandate
        self.policy = policy
        node = self.evidence.add(
            NodeKind.INTENT,
            actor=actor,
            payload=mandate.to_dict(),
        )
        self.evidence.add(
            NodeKind.USER_POLICY,
            actor=actor,
            payload={"policy_hash": policy.fingerprint()},
            node_id=f"user_policy-{policy.fingerprint()[:12]}",
        )
        self.ledger.append(
            EventKind.INTENT_CAPTURED,
            actor=actor,
            detail={
                "mandate_id": mandate.mandate_id,
                "raw_utterance": mandate.raw_utterance,
                "interpreted_by": mandate.interpreted_by,
                "policy_hash": policy.fingerprint(),
            },
        )
        if self.state is State.DRAFT:
            self.move_to(State.INTENT_CAPTURED, actor=actor)
        return node

    # ------------------------------------------------------------------
    # evidence contributed by capabilities
    # ------------------------------------------------------------------

    def contribute(
        self,
        kind: NodeKind,
        *,
        actor: str,
        payload: dict[str, Any] | None = None,
        observations: tuple[Observation, ...] | list[Observation] = (),
        confidence: float | None = None,
        derived_from: str | None = None,
        edge: EdgeKind = EdgeKind.DERIVED_FROM,
        subsystem_ref: tuple[str, str] | None = None,
    ) -> EvidenceNode:
        """Record one capability's contribution to this transaction.

        This is the single entry point every adapter uses, so nothing can join
        the transaction without a provenance-bearing node and a ledger event.
        """
        node = self.evidence.add(
            kind,
            actor=actor,
            payload=payload,
            observations=observations,
            confidence=confidence,
        )
        if derived_from is not None:
            self.evidence.link(derived_from, node.node_id, edge)
        if subsystem_ref is not None:
            name, ref = subsystem_ref
            self.subsystem_refs[name] = ref
        self.ledger.append(
            EventKind.EVIDENCE_RECORDED,
            actor=actor,
            detail={
                "node_id": node.node_id,
                "kind": str(kind),
                "weakest_class": str(node.weakest_class),
                "sandbox": node.is_sandbox,
            },
        )
        return node

    @property
    def has_sandbox_evidence(self) -> bool:
        """True when anything in the graph came from a sandbox adapter.

        Propagates into the contract, so a sandbox price can never quietly
        fund a real purchase (spec Sec. 24).
        """
        return self.evidence.has_sandbox_evidence()

    def evidence_gaps(self) -> tuple[str, ...]:
        """Fields we looked for and could not get, or that conflict.

        Returned so the UI can show ``UNKNOWN`` / ``CONFLICTING_EVIDENCE``
        rather than a plausible-looking number (spec Sec. 11).
        """
        gaps: list[str] = []
        for node in self.evidence.nodes:
            for obs in node.observations:
                if obs.evidence_class in (
                    EvidenceClass.UNAVAILABLE,
                    EvidenceClass.UNKNOWN,
                    EvidenceClass.CONFLICTING,
                ):
                    gaps.append(f"{node.kind}.{obs.field}:{obs.evidence_class}")
        return tuple(gaps)

    # ------------------------------------------------------------------
    # evaluation and contract
    # ------------------------------------------------------------------

    def record_decision(self, decision: Decision, *, actor: str) -> LedgerEvent:
        """Store a policy decision and its reasons, verbatim."""
        return self.ledger.append(
            EventKind.POLICY_EVALUATED,
            actor=actor,
            detail={
                "outcome": str(decision.outcome),
                "explanation": decision.explain(),
                "policy_hash": decision.policy_hash,
            },
        )

    def write_contract(
        self,
        *,
        actor: str,
        product_id: str,
        merchant_id: str,
        expected_amount: Money,
        quantity: int = 1,
        valid_for: timedelta = timedelta(minutes=10),
        max_delivery_days: int | None = None,
        allowed_payment_methods: tuple[str, ...] = (),
        price_tolerance: Money | None = None,
    ) -> TransactionContract:
        """Freeze the terms.  Sandbox provenance propagates automatically."""
        if self.mandate is None or self.policy is None:
            raise ValueError("cannot write a contract before intent is captured")
        contract = TransactionContract.create(
            transaction_id=self.transaction_id,
            mandate=self.mandate,
            policy=self.policy,
            product_id=product_id,
            merchant_id=merchant_id,
            expected_amount=expected_amount,
            quantity=quantity,
            valid_for=valid_for,
            max_delivery_days=max_delivery_days,
            allowed_payment_methods=allowed_payment_methods,
            price_tolerance=price_tolerance,
            sandbox=self.has_sandbox_evidence,
        )
        self.contract = contract
        node = self.evidence.add(
            NodeKind.CONTRACT,
            actor=actor,
            payload=contract.to_dict(),
            node_id=f"contract-{contract.contract_id[-12:]}",
        )
        for intent in self.evidence.of_kind(NodeKind.INTENT):
            self.evidence.link(intent.node_id, node.node_id, EdgeKind.BINDS)
        self.ledger.append(
            EventKind.CONTRACT_CREATED,
            actor=actor,
            detail=contract.to_dict(),
        )
        return contract

    def check_against_reality(
        self, observed: ObservedCheckout, *, actor: str
    ) -> tuple[ContractViolation, ...]:
        """Compare the live cart to the frozen terms at the edge of execution.

        Every violation is reported at once, and a violating checkout moves the
        transaction into the matching exception state rather than continuing
        (spec Sec. 18, Sec. 44).
        """
        if self.contract is None:
            raise ValueError("no contract to check against")
        violations = self.contract.check(observed)
        self.ledger.append(
            EventKind.CHECKOUT_OBSERVED,
            actor=actor,
            detail=observed.to_dict() if hasattr(observed, "to_dict") else {},
        )
        self.ledger.append(
            EventKind.CONTRACT_CHECKED,
            actor=actor,
            detail={
                "violation_count": len(violations),
                "violations": [v.to_dict() for v in violations],
            },
        )
        if violations:
            self.ledger.append(
                EventKind.CONTRACT_VIOLATED,
                actor=actor,
                detail={"violations": [v.to_dict() for v in violations]},
            )
            self.raise_exception(
                kind=str(violations[0].kind),
                actor=actor,
                detail={"violations": [v.to_dict() for v in violations]},
            )
        return violations

    # ------------------------------------------------------------------
    # authorization
    # ------------------------------------------------------------------

    def request_authorization(self, *, actor: str) -> LedgerEvent:
        if self.contract is None:
            raise ValueError("nothing to authorize without a contract")
        if self.state is not State.AWAITING_AUTHORIZATION:
            self.move_to(State.AWAITING_AUTHORIZATION, actor=actor)
        return self.ledger.append(
            EventKind.AUTHORIZATION_REQUESTED,
            actor=actor,
            detail={"contract_id": self.contract.contract_id},
        )

    def grant_authorization(
        self, authorization: Authorization, *, actor: str
    ) -> Authorization:
        """Attach the user's consent.

        The ``Authorization`` carries the user's own words and is bound to one
        contract by ``binding_hash``; if the terms changed it is already dead
        and this refuses it.
        """
        if self.contract is None:
            raise ValueError("no contract for this authorization")
        reason = authorization.invalid_reason(self.contract)
        if reason is not None:
            # Record the refusal: a rejected consent is as auditable as a
            # granted one, so a retry loop cannot hide it.
            self.ledger.append(
                EventKind.AGENT_ACTION_REFUSED,
                actor=actor,
                detail={
                    "action": "grant_authorization",
                    "authorization_id": authorization.authorization_id,
                    "reason": reason,
                },
            )
            raise ValueError(f"authorization does not cover this contract: {reason}")
        self.authorization = authorization
        node = self.evidence.add(
            NodeKind.AUTHORIZATION,
            actor=actor,
            payload=authorization.to_dict(),
        )
        contract_nodes = self.evidence.of_kind(NodeKind.CONTRACT)
        if contract_nodes:
            self.evidence.link(
                node.node_id, contract_nodes[-1].node_id, EdgeKind.AUTHORIZES
            )
        self.ledger.append(
            EventKind.AUTHORIZATION_GRANTED,
            actor=actor,
            detail={
                "authorization_id": authorization.authorization_id,
                "quote": authorization.transcript_quote,
                "expires_at": (
                    authorization.expires_at.isoformat()
                    if authorization.expires_at
                    else None
                ),
            },
        )
        self.move_to(State.AUTHORIZED, actor=actor)
        return authorization

    # ------------------------------------------------------------------
    # exceptions and resolution
    # ------------------------------------------------------------------

    def raise_exception(
        self,
        *,
        kind: str,
        actor: str,
        detail: dict[str, Any] | None = None,
        target: State | None = None,
    ) -> LedgerEvent:
        """Record an exception and move to the matching state if it is legal.

        Never hides an error: if the lifecycle does not allow the exception
        state from here, the exception is still logged and the transaction is
        sent to ``REVIEW_REQUIRED`` where a human sees it (spec Sec. 32).
        """
        entry = {"kind": kind, "at": utcnow().isoformat(), **(detail or {})}
        self.exceptions.append(entry)
        event = self.ledger.append(
            EventKind.EXCEPTION_RAISED,
            actor=actor,
            detail=entry,
            state_before=self.state,
        )
        self.evidence.add(NodeKind.EXCEPTION, actor=actor, payload=entry)
        candidates: list[State] = []
        if target is not None:
            candidates.append(target)
        named = _STATE_BY_NAME.get(kind)
        if named is not None:
            candidates.append(named)
        candidates.append(State.REVIEW_REQUIRED)
        for candidate in candidates:
            try:
                self.move_to(candidate, actor=actor, detail={"exception": kind})
                break
            except IllegalTransition:
                continue
        return event

    def resolve(
        self, *, actor: str, resolution: dict[str, Any], node_id: str | None = None
    ) -> LedgerEvent:
        """Close out the open exceptions with a recorded outcome."""
        node = self.evidence.add(
            NodeKind.RESOLUTION, actor=actor, payload=resolution, node_id=node_id
        )
        for exc in self.evidence.of_kind(NodeKind.EXCEPTION):
            self.evidence.link(node.node_id, exc.node_id, EdgeKind.RESOLVES)
        event = self.ledger.append(EventKind.RESOLVED, actor=actor, detail=resolution)
        self.exceptions.clear()
        return event

    # ------------------------------------------------------------------
    # audit
    # ------------------------------------------------------------------

    def verify_integrity(self) -> tuple[bool, str]:
        """Re-verify the ledger hash chain.

        Returns ``(ok, message)``; the message names the sequence number of the
        break when ``ok`` is False, and reports the chain length when it holds.
        """
        return self.ledger.verify_chain()

    def timeline(self) -> list[dict[str, Any]]:
        """The lifecycle as the UI shows it (spec Sec. 35)."""
        return [e.to_dict() for e in self.ledger.events]

    def to_dict(self) -> dict[str, Any]:
        """The universal transaction shape (spec Sec. 5)."""
        ok, integrity_message = self.verify_integrity()
        return {
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
            "transaction_type": self.transaction_type,
            "state": str(self.state),
            "is_open": self.is_open,
            "is_cancellable": self.is_cancellable,
            "created_at": self.created_at.isoformat(),
            "intent": self.mandate.to_dict() if self.mandate else None,
            "policy_hash": self.policy.fingerprint() if self.policy else None,
            "contract": self.contract.to_dict() if self.contract else None,
            "authorization": (
                self.authorization.to_dict() if self.authorization else None
            ),
            "checkout_mandate": (
                self.checkout_mandate.to_dict() if self.checkout_mandate else None
            ),
            "payment_mandate": (
                self.payment_mandate.to_dict() if self.payment_mandate else None
            ),
            "subsystem_refs": dict(self.subsystem_refs),
            "sandbox": self.has_sandbox_evidence,
            "evidence_gaps": list(self.evidence_gaps()),
            "exceptions": list(self.exceptions),
            "evidence_graph": self.evidence.reconstruct(),
            "audit_log": self.timeline(),
            "ledger_intact": ok,
            "ledger_integrity": integrity_message,
            "in_flight_payments": list(self.idempotency.in_flight()),
        }


# Exception kind -> the lifecycle state that names it, so ``raise_exception``
# can route by name without a second table to keep in sync.
_STATE_BY_NAME: dict[str, State] = {str(s): s for s in State}
