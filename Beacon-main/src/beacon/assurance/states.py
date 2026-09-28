"""The transaction lifecycle: states, transitions and the exception lattice.

One object moves through this machine.  Nothing else in the assurance layer
is allowed to invent a status string: every status below is a member of
:class:`State`, and every legal move is an edge in :data:`TRANSITIONS`.

The rule that matters: an LLM may *recommend* a transition, it may never
perform one.  :func:`assert_transition` is plain Python with no model in the
call path, and the ledger records a move only after this function allows it.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "EXCEPTION_STATES",
    "IRREVERSIBLE_AFTER",
    "OPEN_STATES",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "IllegalTransition",
    "State",
    "assert_transition",
    "can_transition",
    "is_open",
    "reachable_from",
]


class State(StrEnum):
    """Every status a transaction may hold.  No other value is valid."""

    # --- happy path -----------------------------------------------------
    DRAFT = "DRAFT"
    INTENT_CAPTURED = "INTENT_CAPTURED"
    DISCOVERING = "DISCOVERING"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    EVALUATING = "EVALUATING"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    FULFILLMENT_PENDING = "FULFILLMENT_PENDING"
    FULFILLMENT_IN_PROGRESS = "FULFILLMENT_IN_PROGRESS"
    FULFILLMENT_COMPLETED = "FULFILLMENT_COMPLETED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    SETTLED = "SETTLED"
    COMPLETED = "COMPLETED"

    # --- exceptions -----------------------------------------------------
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
    PRICE_CHANGED = "PRICE_CHANGED"
    MERCHANT_CHANGED = "MERCHANT_CHANGED"
    PRODUCT_CHANGED = "PRODUCT_CHANGED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    FULFILLMENT_FAILED = "FULFILLMENT_FAILED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    DISPUTE_REQUIRED = "DISPUTE_REQUIRED"
    REFUND_REQUIRED = "REFUND_REQUIRED"
    RESOLUTION_PENDING = "RESOLUTION_PENDING"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


EXCEPTION_STATES: frozenset[State] = frozenset(
    {
        State.REVIEW_REQUIRED,
        State.AUTHORIZATION_EXPIRED,
        State.PRICE_CHANGED,
        State.MERCHANT_CHANGED,
        State.PRODUCT_CHANGED,
        State.PAYMENT_FAILED,
        State.FULFILLMENT_FAILED,
        State.DELIVERY_FAILED,
        State.VERIFICATION_FAILED,
        State.RECONCILIATION_FAILED,
        State.DISPUTE_REQUIRED,
        State.REFUND_REQUIRED,
        State.RESOLUTION_PENDING,
    }
)

TERMINAL_STATES: frozenset[State] = frozenset(
    {State.COMPLETED, State.RESOLVED, State.CANCELLED}
)

# Past this point money has moved, so recovery is a refund or a dispute --
# never a silent rewind.  ``Transaction.is_cancellable`` reads this.
IRREVERSIBLE_AFTER: frozenset[State] = frozenset(
    {
        State.PAYMENT_COMPLETED,
        State.FULFILLMENT_PENDING,
        State.FULFILLMENT_IN_PROGRESS,
        State.FULFILLMENT_COMPLETED,
        State.VERIFYING,
        State.VERIFIED,
        State.SETTLED,
    }
)

# Any pre-payment state may be abandoned by the user, and any live state may
# hit review.  Spelling these once keeps the table to the interesting edges.
_UNIVERSAL: frozenset[State] = frozenset({State.CANCELLED, State.REVIEW_REQUIRED})

TRANSITIONS: dict[State, frozenset[State]] = {
    State.DRAFT: frozenset({State.INTENT_CAPTURED}) | _UNIVERSAL,
    State.INTENT_CAPTURED: frozenset({State.DISCOVERING}) | _UNIVERSAL,
    State.DISCOVERING: frozenset({State.EVIDENCE_COLLECTION}) | _UNIVERSAL,
    State.EVIDENCE_COLLECTION: frozenset({State.EVALUATING}) | _UNIVERSAL,
    State.EVALUATING: frozenset({State.AWAITING_AUTHORIZATION}) | _UNIVERSAL,
    State.AWAITING_AUTHORIZATION: (
        frozenset({State.AUTHORIZED, State.AUTHORIZATION_EXPIRED}) | _UNIVERSAL
    ),
    # A contract is re-checked at the edge of execution, so the drift
    # exceptions hang off AUTHORIZED and EXECUTING, not off evaluation.
    State.AUTHORIZED: (
        frozenset(
            {
                State.EXECUTING,
                State.AUTHORIZATION_EXPIRED,
                State.PRICE_CHANGED,
                State.MERCHANT_CHANGED,
                State.PRODUCT_CHANGED,
            }
        )
        | _UNIVERSAL
    ),
    State.EXECUTING: (
        frozenset(
            {
                State.PAYMENT_PENDING,
                State.PRICE_CHANGED,
                State.MERCHANT_CHANGED,
                State.PRODUCT_CHANGED,
                State.AUTHORIZATION_EXPIRED,
            }
        )
        | _UNIVERSAL
    ),
    State.PAYMENT_PENDING: (
        frozenset({State.PAYMENT_AUTHORIZED, State.PAYMENT_FAILED}) | _UNIVERSAL
    ),
    State.PAYMENT_AUTHORIZED: (
        frozenset({State.PAYMENT_COMPLETED, State.PAYMENT_FAILED}) | _UNIVERSAL
    ),
    # Money has moved.  CANCELLED is gone from here on: the only ways out are
    # fulfilment, or a refund / dispute path.
    State.PAYMENT_COMPLETED: frozenset(
        {State.FULFILLMENT_PENDING, State.REFUND_REQUIRED, State.REVIEW_REQUIRED}
    ),
    State.FULFILLMENT_PENDING: frozenset(
        {
            State.FULFILLMENT_IN_PROGRESS,
            State.FULFILLMENT_FAILED,
            State.REFUND_REQUIRED,
            State.REVIEW_REQUIRED,
        }
    ),
    State.FULFILLMENT_IN_PROGRESS: frozenset(
        {
            State.FULFILLMENT_COMPLETED,
            State.FULFILLMENT_FAILED,
            State.DELIVERY_FAILED,
            State.REVIEW_REQUIRED,
        }
    ),
    State.FULFILLMENT_COMPLETED: frozenset({State.VERIFYING, State.REVIEW_REQUIRED}),
    State.VERIFYING: frozenset(
        {State.VERIFIED, State.VERIFICATION_FAILED, State.REVIEW_REQUIRED}
    ),
    State.VERIFIED: frozenset(
        {State.SETTLED, State.RECONCILIATION_FAILED, State.REVIEW_REQUIRED}
    ),
    State.SETTLED: frozenset(
        {State.COMPLETED, State.RECONCILIATION_FAILED, State.REVIEW_REQUIRED}
    ),
    # Terminal, but a late chargeback reopens via DISPUTE_REQUIRED.
    State.COMPLETED: frozenset({State.DISPUTE_REQUIRED}),
    # --- exception handling --------------------------------------------
    # Drift exceptions are recoverable: re-evaluate and ask again.
    State.PRICE_CHANGED: frozenset(
        {State.EVALUATING, State.DISCOVERING, State.CANCELLED, State.REVIEW_REQUIRED}
    ),
    State.MERCHANT_CHANGED: frozenset(
        {State.EVALUATING, State.DISCOVERING, State.CANCELLED, State.REVIEW_REQUIRED}
    ),
    State.PRODUCT_CHANGED: frozenset(
        {State.EVALUATING, State.DISCOVERING, State.CANCELLED, State.REVIEW_REQUIRED}
    ),
    State.AUTHORIZATION_EXPIRED: frozenset(
        {State.AWAITING_AUTHORIZATION, State.CANCELLED}
    ),
    State.REVIEW_REQUIRED: frozenset(
        {
            State.EVALUATING,
            State.AWAITING_AUTHORIZATION,
            State.RESOLUTION_PENDING,
            State.CANCELLED,
        }
    ),
    State.PAYMENT_FAILED: frozenset(
        {State.PAYMENT_PENDING, State.CANCELLED, State.RESOLUTION_PENDING}
    ),
    State.FULFILLMENT_FAILED: frozenset(
        {State.REFUND_REQUIRED, State.DISPUTE_REQUIRED, State.RESOLUTION_PENDING}
    ),
    State.DELIVERY_FAILED: frozenset(
        {State.REFUND_REQUIRED, State.DISPUTE_REQUIRED, State.RESOLUTION_PENDING}
    ),
    State.VERIFICATION_FAILED: frozenset(
        {
            State.REFUND_REQUIRED,
            State.DISPUTE_REQUIRED,
            State.RESOLUTION_PENDING,
            State.REVIEW_REQUIRED,
        }
    ),
    State.RECONCILIATION_FAILED: frozenset(
        {State.RESOLUTION_PENDING, State.DISPUTE_REQUIRED, State.REVIEW_REQUIRED}
    ),
    State.REFUND_REQUIRED: frozenset(
        {State.RESOLUTION_PENDING, State.DISPUTE_REQUIRED, State.RESOLVED}
    ),
    State.DISPUTE_REQUIRED: frozenset({State.RESOLUTION_PENDING, State.RESOLVED}),
    State.RESOLUTION_PENDING: frozenset(
        {State.RESOLVED, State.DISPUTE_REQUIRED, State.REVIEW_REQUIRED}
    ),
    State.RESOLVED: frozenset(),
    State.CANCELLED: frozenset(),
}

OPEN_STATES: frozenset[State] = frozenset(TRANSITIONS) - TERMINAL_STATES


class IllegalTransition(ValueError):
    """Raised when a caller attempts a move the lifecycle does not allow."""

    def __init__(self, current: State, target: State) -> None:
        self.current = current
        self.target = target
        allowed = ", ".join(sorted(TRANSITIONS.get(current, frozenset()))) or "(none)"
        super().__init__(
            f"cannot move {current} -> {target}; allowed from {current}: {allowed}"
        )


def can_transition(current: State, target: State) -> bool:
    """True when *target* is a declared successor of *current*."""
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: State, target: State) -> None:
    """Raise :class:`IllegalTransition` unless the move is declared legal."""
    if not can_transition(current, target):
        raise IllegalTransition(current, target)


def is_open(state: State) -> bool:
    """True while the transaction still needs attention.

    Payment success is *not* completion: a transaction stays open through
    fulfilment, verification and settlement.
    """
    return state not in TERMINAL_STATES


def reachable_from(state: State) -> frozenset[State]:
    """Every state reachable from *state*, for tests and UI affordances."""
    seen: set[State] = set()
    frontier = [state]
    while frontier:
        node = frontier.pop()
        for nxt in TRANSITIONS.get(node, frozenset()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return frozenset(seen)
