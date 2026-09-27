"""The thin PeoplePay agent shell -- Phase 4.

The agent is the *interface*.  The engine is the brain.  Concretely, that means
this module contains no policy, no money arithmetic and no state transitions of
its own: it turns an utterance into a mandate, calls tools, and reports back.

The nine tools in ``ToolRegistry`` are the only way the agent touches a
transaction (§21).  There is deliberately no ``execute``, no ``pay`` and no
``book`` -- §20 says execution comes later, and an absent tool is a stronger
guarantee than a disabled one.

Every tool checks, in this order:

1. the caller owns the transaction (§26, invariant 1)
2. the permission the tool needs is actually granted (§25, invariants 6-7)
3. only then does it touch the aggregate

Language handling follows §22: the raw utterance is never replaced.
``detect_language`` and ``parse_budget`` read it and produce *derived* values
that sit beside it.  A translation is an interpretation, not a consent record.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from beacon.assurance import (
    AutonomyLevel,
    EventKind,
    IntentMandate,
    Money,
    State,
)
from beacon.peoplepay.authority import (
    AuthorityError,
    ConditionalGrant,
    Permission,
    TransactionType,
)
from beacon.peoplepay.memory import MemoryVault
from beacon.peoplepay.nodes import PeoplePayNodeKind, Retention, SourceType
from beacon.peoplepay.transaction import Transaction

__all__ = [
    "AgentResponse",
    "PeoplePayAgent",
    "ResponseKind",
    "ToolRegistry",
    "detect_language",
    "parse_budget",
]


# --- language, without replacing the original ----------------------------

_TAMIL = re.compile(r"[஀-௿]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(utterance: str) -> str:
    """Return a coarse language tag for ``utterance``.

    ``"ta"`` Tamil script, ``"en"`` Latin only, ``"ta-Latn"`` mixed -- the
    "Tanglish" case the brief calls out, which is genuinely neither.  Returns
    ``"und"`` (undetermined) rather than guessing when there is no signal;
    ISO 639-2 reserves ``und`` for exactly this.
    """
    has_tamil = bool(_TAMIL.search(utterance))
    has_latin = bool(_LATIN.search(utterance))
    if has_tamil and has_latin:
        return "ta-Latn"
    if has_tamil:
        return "ta"
    if has_latin:
        return "en"
    return "und"


_BUDGET = re.compile(
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:rupees|ரூபாய)",
    re.IGNORECASE,
)


def parse_budget(utterance: str, *, currency: str = "INR") -> Money | None:
    """Extract a budget from ``utterance``, or ``None`` if none is stated.

    Returns ``None`` rather than a default: "the user did not say" is a real
    answer and must not become "the user said zero" or "unlimited".  Digits are
    normalised through ``unicodedata`` so Tamil numerals parse too, and the
    amount goes through ``Money.of`` on a ``str`` -- never a float.
    """
    normalized = "".join(
        str(unicodedata.decimal(ch)) if ch.isdigit() and not ch.isascii() else ch
        for ch in utterance
    )
    match = _BUDGET.search(normalized)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    if not raw:
        return None
    try:
        return Money.of(Decimal(raw.replace(",", "")), currency)
    except (ValueError, ArithmeticError):
        return None


# --- what the agent may say ----------------------------------------------


class ResponseKind(StrEnum):
    """The kinds of thing the agent can return (§23).

    Distinct members because a plan and an authorization request are read very
    differently by a caller, and collapsing them invites a UI that treats a
    request for consent as information.
    """

    ANSWER = "ANSWER"
    QUESTION = "QUESTION"
    PLAN = "PLAN"
    ACTION_REQUEST = "ACTION_REQUEST"
    AUTHORIZATION_REQUEST = "AUTHORIZATION_REQUEST"
    ACTION_RESULT = "ACTION_RESULT"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class AgentResponse:
    """One reply, with what it rests on and what it would need."""

    kind: ResponseKind
    text: str
    transaction_id: str | None = None
    evidence: tuple[str, ...] = ()
    permissions_required: tuple[Permission, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "text": self.text,
            "transaction_id": self.transaction_id,
            "evidence": list(self.evidence),
            "permissions_required": [str(p) for p in self.permissions_required],
            "detail": self.detail,
        }


# --- the nine tools ------------------------------------------------------


class ToolRegistry:
    """The only surface through which the agent touches a transaction (§21).

    Holds transactions and vaults in memory for Phase 4.  Persistence arrives
    with the store; the point of this class is that the *authorization checks*
    live at the boundary, so a later store swap cannot lose them.
    """

    def __init__(self) -> None:
        self._transactions: dict[str, Transaction] = {}
        self._vaults: dict[str, MemoryVault] = {}

    # --- helpers ----------------------------------------------------------

    def vault(self, user_id: str) -> MemoryVault:
        """The user's vault, created on first use."""
        if user_id not in self._vaults:
            self._vaults[user_id] = MemoryVault(user_id)
        return self._vaults[user_id]

    def _owned(self, transaction_id: str, user_id: str) -> Transaction:
        txn = self._transactions.get(transaction_id)
        if txn is None:
            raise KeyError(f"no transaction {transaction_id!r}")
        txn.assert_owned_by(user_id)
        return txn

    # --- 1 ----------------------------------------------------------------

    def create_transaction(
        self,
        *,
        user_id: str,
        raw_utterance: str,
        transaction_type: TransactionType = TransactionType.PURCHASE,
        language: str | None = None,
    ) -> Transaction:
        """Open a transaction.  Needs no permission -- it commits to nothing."""
        txn = Transaction.create(
            user_id=user_id,
            raw_utterance=raw_utterance,
            transaction_type=transaction_type,
            language=language or detect_language(raw_utterance),
        )
        self._transactions[txn.transaction_id] = txn
        return txn

    # --- 2 ----------------------------------------------------------------

    def get_transaction(self, transaction_id: str, *, user_id: str) -> Transaction:
        """Read one transaction, if it is the caller's."""
        return self._owned(transaction_id, user_id)

    # --- 3 ----------------------------------------------------------------

    def get_user_memory(
        self, *, user_id: str, include_inferences: bool = False
    ) -> list[dict[str, Any]]:
        """Read long-term memory.  Inferences withheld unless asked for."""
        items = self.vault(user_id).get_user_memory(
            include_inferences=include_inferences
        )
        return [i.to_dict() for i in items]

    # --- 4 ----------------------------------------------------------------

    def get_transaction_history(
        self, *, user_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """The caller's own past transactions, newest first."""
        mine = [t for t in self._transactions.values() if t.user_id == user_id]
        mine.sort(key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in mine[:limit]]

    # --- 5 ----------------------------------------------------------------

    def add_evidence(
        self,
        transaction_id: str,
        *,
        user_id: str,
        kind: PeoplePayNodeKind,
        source: str,
        source_type: SourceType,
        payload: dict[str, Any] | None = None,
        sandbox: bool = False,
    ) -> str:
        """Record evidence.  Requires DISCOVERY."""
        txn = self._owned(transaction_id, user_id)
        txn.require_permission(Permission.DISCOVERY)
        return txn.add_evidence(
            kind,
            actor="peoplepay.agent",
            source=source,
            source_type=source_type,
            payload=payload,
            sandbox=sandbox,
        )

    # --- 6 ----------------------------------------------------------------

    def add_context(
        self,
        transaction_id: str,
        *,
        user_id: str,
        slot: str,
        payload: dict[str, Any],
    ) -> None:
        """Attach capability context.  Requires DISCOVERY."""
        txn = self._owned(transaction_id, user_id)
        txn.require_permission(Permission.DISCOVERY)
        txn.attach_context(slot, payload, actor="peoplepay.agent")

    # --- 7 ----------------------------------------------------------------

    def create_plan(
        self,
        transaction_id: str,
        *,
        user_id: str,
        summary: str,
        steps: tuple[str, ...],
        estimated_amount: Money | None = None,
    ) -> dict[str, Any]:
        """Assemble a proposal.  Requires PLANNING, and executes nothing."""
        txn = self._owned(transaction_id, user_id)
        txn.require_permission(Permission.PLANNING)
        plan = {
            "summary": summary,
            "steps": list(steps),
            "estimated_amount": (
                estimated_amount.to_dict() if estimated_amount else None
            ),
            "executed": False,
            "rests_on_sandbox_evidence": txn.has_sandbox_evidence,
        }
        txn.plan = plan
        txn.ledger.append(
            EventKind.POLICY_EVALUATED,
            actor="peoplepay.agent",
            detail={"plan_summary": summary, "steps": len(steps)},
        )
        return plan

    # --- 8 ----------------------------------------------------------------

    def validate_plan(self, transaction_id: str, *, user_id: str) -> dict[str, Any]:
        """Check a plan for the problems code can see without a provider.

        Deliberately conservative: it reports what is missing rather than
        deciding the purchase is fine.  A plan resting on sandbox evidence is
        never valid for execution (§12).
        """
        txn = self._owned(transaction_id, user_id)
        txn.require_permission(Permission.PLANNING)
        problems: list[str] = []
        if txn.plan is None:
            problems.append("no plan has been created")
        if txn.mandate is None:
            problems.append("no intent mandate is attached")
        if txn.has_sandbox_evidence:
            problems.append(
                "plan rests on sandbox evidence, which cannot support execution"
            )
        if txn.plan and txn.mandate and txn.mandate.max_amount is not None:
            est = txn.plan.get("estimated_amount")
            if est is None:
                problems.append("plan has no estimated amount to check against budget")
            elif est["currency"] != txn.mandate.max_amount.currency:
                problems.append(
                    f"plan currency {est['currency']} does not match mandate "
                    f"currency {txn.mandate.max_amount.currency}"
                )
            elif est["minor"] > txn.mandate.max_amount.minor:
                problems.append("estimated amount exceeds the user's stated budget")
        result = {"valid": not problems, "problems": problems}
        txn.ledger.append(
            EventKind.CONTRACT_CHECKED,
            actor="peoplepay.agent",
            detail=result,
        )
        return result

    # --- 9 ----------------------------------------------------------------

    def request_authorization(
        self,
        transaction_id: str,
        *,
        user_id: str,
        permission: Permission,
        amount: Money | None = None,
        reason: str = "",
    ) -> AgentResponse:
        """Ask the user for a permission.  Never grants it.

        Returns an ``AUTHORIZATION_REQUEST`` for the caller to put in front of
        the user.  The agent cannot authorize on the user's behalf, which is why
        this returns a request rather than a boolean.
        """
        txn = self._owned(transaction_id, user_id)
        txn.ledger.append(
            EventKind.AUTHORIZATION_REQUESTED,
            actor="peoplepay.agent",
            detail={
                "permission": str(permission),
                "amount": amount.to_dict() if amount else None,
                "reason": reason,
                "outcome": "PENDING",
            },
        )
        if txn.state is State.EVALUATING:
            txn.transition_to(State.AWAITING_AUTHORIZATION, actor="peoplepay.agent")
        return AgentResponse(
            kind=ResponseKind.AUTHORIZATION_REQUEST,
            text=reason or f"{permission} permission is needed before continuing.",
            transaction_id=transaction_id,
            permissions_required=(permission,),
            detail={"amount": amount.to_dict() if amount else None},
        )


# --- the agent -----------------------------------------------------------


class PeoplePayAgent:
    """Turns what a person said into a transaction, a plan, and a question.

    The agent holds no authority of its own.  It reads memory, records evidence,
    proposes, and asks -- and when it wants something consequential it returns
    an ``AUTHORIZATION_REQUEST`` instead of doing it.
    """

    actor = "peoplepay.agent"

    def __init__(self, tools: ToolRegistry | None = None) -> None:
        self.tools = tools or ToolRegistry()

    # --- turn 1: intent ---------------------------------------------------

    def handle_intent(
        self,
        *,
        user_id: str,
        utterance: str,
        product_query: str,
        transaction_type: TransactionType = TransactionType.PURCHASE,
        interpreted_by: str | None = None,
    ) -> tuple[Transaction, AgentResponse]:
        """Open a transaction from an utterance and report what is allowed.

        ``product_query`` is the normalised reading.  It is passed in rather
        than parsed here because normalisation is a model's job and this shell
        must not pretend to be the model -- but the raw utterance, which *is*
        the consent record, is stored untouched either way.
        """
        language = detect_language(utterance)
        txn = self.tools.create_transaction(
            user_id=user_id,
            raw_utterance=utterance,
            transaction_type=transaction_type,
            language=language,
        )
        budget = parse_budget(utterance)
        mandate = IntentMandate.create(
            user_id=user_id,
            raw_utterance=utterance,
            product_query=product_query,
            max_amount=budget,
            autonomy=AutonomyLevel.HUMAN_PRESENT,
            interpreted_by=interpreted_by,
        )
        txn.capture_intent(mandate, normalized_intent=product_query, actor=self.actor)

        vault = self.tools.vault(user_id)
        vault.remember(
            kind=PeoplePayNodeKind.USER_FACT,
            key="last_intent",
            value=product_query,
            source=SourceType.SELF_REPORTED,
            retention=Retention.TRANSACTION_ONLY,
            transaction_id=txn.transaction_id,
        )
        txn.memory_refs = tuple(
            i.item_id for i in vault.get_transaction_memory(txn.transaction_id)
        )

        allowed = sorted(str(p) for p in txn.permissions.granted)
        budget_text = f" Budget understood as {budget}." if budget else ""
        _VERBS = {
            "DISCOVERY": "search",
            "PLANNING": "put together a plan",
            "BOOKING": "book",
            "PAYMENT": "pay",
            "SHARING": "share your details",
        }
        can_do = " and ".join(_VERBS.get(a, a.lower()) for a in allowed)
        return txn, AgentResponse(
            kind=ResponseKind.ANSWER,
            text=(
                f"Understood: {product_query}.{budget_text} "
                f"I can {can_do}. "
                "I will ask before booking or paying for anything."
            ),
            transaction_id=txn.transaction_id,
            detail={
                "language": language,
                "raw_utterance_preserved": txn.raw_utterance == utterance,
                "budget": budget.to_dict() if budget else None,
                "granted": allowed,
            },
        )

    # --- turn 2: conditional authority ------------------------------------

    def handle_conditional_authorization(
        self,
        transaction_id: str,
        *,
        user_id: str,
        utterance: str,
        permission: Permission = Permission.PAYMENT,
    ) -> AgentResponse:
        """Record "buy it if it is under X" as a bounded grant (§24).

        The cap comes from the utterance.  With no parsable cap this refuses
        rather than granting unbounded authority -- an ambiguous consent to
        spend is not a consent to spend anything.
        """
        txn = self.tools.get_transaction(transaction_id, user_id=user_id)
        cap = parse_budget(utterance)
        if cap is None:
            return AgentResponse(
                kind=ResponseKind.QUESTION,
                text=(
                    "I did not catch a price limit in that. What is the most I "
                    "should pay?"
                ),
                transaction_id=transaction_id,
                permissions_required=(permission,),
            )
        grant = ConditionalGrant(
            permission=permission,
            max_amount=cap,
            raw_utterance=utterance,
        )
        txn.grant_conditional(grant, actor=self.actor)
        txn.permissions = txn.permissions.with_autonomy(AutonomyLevel.CONDITIONAL)
        return AgentResponse(
            kind=ResponseKind.ACTION_RESULT,
            text=(
                f"Recorded: I may pay up to {cap}, and only up to {cap}. "
                "Anything above that comes back to you."
            ),
            transaction_id=transaction_id,
            detail={
                "conditional_grant": grant.to_dict(),
                "autonomy": str(txn.permissions.autonomy),
            },
        )

    # --- refusal path -----------------------------------------------------

    def attempt_payment(
        self,
        transaction_id: str,
        *,
        user_id: str,
        amount: Money,
    ) -> AgentResponse:
        """Try to pay, and report honestly when it is not permitted.

        Phase 4 has no payment provider, so a *permitted* payment still does not
        execute: it returns ``ACTION_REQUEST`` naming what is missing.  There is
        no code path here that reports a payment as completed, which is what §27
        means by never creating fake success events.
        """
        txn = self.tools.get_transaction(transaction_id, user_id=user_id)
        try:
            txn.require_permission(Permission.PAYMENT, amount=amount, actor=self.actor)
        except AuthorityError as exc:
            return AgentResponse(
                kind=ResponseKind.AUTHORIZATION_REQUEST,
                text=(
                    f"I cannot pay {amount} yet: {exc}. Tell me to go ahead and "
                    "I will ask you to confirm the exact amount."
                ),
                transaction_id=transaction_id,
                permissions_required=(Permission.PAYMENT,),
            )
        return AgentResponse(
            kind=ResponseKind.ACTION_REQUEST,
            text=(
                f"Payment of {amount} is authorized by your instruction, but no "
                "payment provider is connected yet, so nothing has been paid."
            ),
            transaction_id=transaction_id,
            detail={"provider_status": "NOT_CONFIGURED", "executed": False},
        )
