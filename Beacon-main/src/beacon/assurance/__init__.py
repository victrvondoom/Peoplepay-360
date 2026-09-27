"""Transaction Assurance Engine.

One object -- the transaction -- moves through one deterministic lifecycle,
and every capability in this package operates on it.  The layering is the
point: a model may read, propose and explain, but the decisions that move
money are taken by plain Python that a test can pin down.

    money       exact amounts; integer minor units, never floats
    states      the lifecycle and its legal transitions
    evidence    provenance, evidence classes, the append-only evidence graph
    policy      the intent mandate and the deterministic policy engine
    contract    frozen terms, drift detection, scoped authorization, mandates
    ledger      the hash-chained event log and the idempotency guard

What is deliberately *not* here: a payment network.  This layer decides why,
what, for whom, how much and under what conditions; a payment provider moves
the money.

See ``docs/assurance.md`` for the design and the reasoning behind each rule.
"""

from __future__ import annotations

from beacon.assurance.contract import (
    Authorization,
    CheckoutMandate,
    ContractViolation,
    ObservedCheckout,
    PaymentMandate,
    TransactionContract,
    ViolationKind,
)
from beacon.assurance.evidence import (
    EdgeKind,
    EvidenceClass,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    NodeKind,
    Observation,
    Provenance,
    conflicting,
    content_hash,
    unavailable,
    utcnow,
)
from beacon.assurance.ledger import (
    EventKind,
    IdempotencyConflict,
    IdempotencyGuard,
    LedgerEvent,
    TransactionLedger,
)
from beacon.assurance.money import MINOR_UNITS, CurrencyMismatch, Money
from beacon.assurance.policy import (
    AutonomyLevel,
    Candidate,
    Decision,
    IntentMandate,
    Outcome,
    Policy,
    PolicyEngine,
    Reason,
)
from beacon.assurance.states import (
    EXCEPTION_STATES,
    IRREVERSIBLE_AFTER,
    OPEN_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    IllegalTransition,
    State,
    assert_transition,
    can_transition,
    is_open,
    reachable_from,
)

__all__ = [
    "EXCEPTION_STATES",
    "IRREVERSIBLE_AFTER",
    "MINOR_UNITS",
    "OPEN_STATES",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "Authorization",
    "AutonomyLevel",
    "Candidate",
    "CheckoutMandate",
    "ContractViolation",
    "CurrencyMismatch",
    "Decision",
    "EdgeKind",
    "EventKind",
    "EvidenceClass",
    "EvidenceEdge",
    "EvidenceGraph",
    "EvidenceNode",
    "IdempotencyConflict",
    "IdempotencyGuard",
    "IllegalTransition",
    "IntentMandate",
    "LedgerEvent",
    "Money",
    "NodeKind",
    "Observation",
    "ObservedCheckout",
    "Outcome",
    "PaymentMandate",
    "Policy",
    "PolicyEngine",
    "Provenance",
    "Reason",
    "State",
    "TransactionContract",
    "TransactionLedger",
    "ViolationKind",
    "assert_transition",
    "can_transition",
    "conflicting",
    "content_hash",
    "is_open",
    "reachable_from",
    "unavailable",
    "utcnow",
]
