"""The intent mandate and the policy engine.

This module is the seam between language and money.  A model may read
"buy me a laptop under eighty thousand, must arrive this week" and *propose*
an :class:`IntentMandate`; from that point on, every decision that could move
money is taken by :meth:`PolicyEngine.evaluate`, which is ordinary Python and
has no model in its call path.

Three ideas do the work:

* An :class:`IntentMandate` records what the user actually authorized --
  never more.  A vague sentence does not become unlimited authority: fields
  the user did not specify stay ``None``, and an unspecified ceiling means
  *no permission to spend*, not an infinite budget.
* A :class:`Policy` is machine-readable and deterministic.
* A :class:`Decision` always carries its reasons and the evidence it used, so
  the "why" is a value in the system rather than a paragraph a model wrote.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from beacon.assurance.evidence import EvidenceClass, Observation, content_hash, utcnow
from beacon.assurance.money import Money

__all__ = [
    "AutonomyLevel",
    "Candidate",
    "Decision",
    "IntentMandate",
    "Outcome",
    "Policy",
    "PolicyEngine",
    "Reason",
]


class AutonomyLevel(StrEnum):
    """The three human-in-the-loop modes, as a value the engine branches on."""

    HUMAN_PRESENT = "HUMAN_PRESENT"
    """Mode 1: the user approves this specific transaction, in the moment."""

    CONDITIONAL = "CONDITIONAL"
    """Mode 2: the user pre-stated conditions ("buy if under X")."""

    AUTONOMOUS = "AUTONOMOUS"
    """Mode 3: permitted only against a valid pre-authorized contract."""


class Outcome(StrEnum):
    """What the deterministic engine decided."""

    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class Reason:
    """One machine-readable ground for a decision.

    ``code`` is stable and greppable; ``detail`` is for humans.  ``evidence``
    names the observations or nodes consulted, so a decision can be audited
    without re-running it.
    """

    code: str
    detail: str
    outcome: Outcome
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "outcome": str(self.outcome),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class Decision:
    """The engine's verdict.  Never produced by a model."""

    outcome: Outcome
    reasons: tuple[Reason, ...]
    evaluated_at: datetime
    policy_hash: str

    @property
    def allowed(self) -> bool:
        return self.outcome is Outcome.ALLOW

    @property
    def blocking_reasons(self) -> tuple[Reason, ...]:
        return tuple(r for r in self.reasons if r.outcome is Outcome.BLOCK)

    def explain(self) -> str:
        """The explanation, assembled from the reasons actually used."""
        if not self.reasons:
            return f"{self.outcome}: no policy rule applied."
        lines = [f"{self.outcome}:"]
        lines.extend(f"  [{r.outcome}] {r.code}: {r.detail}" for r in self.reasons)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": str(self.outcome),
            "reasons": [r.to_dict() for r in self.reasons],
            "evaluated_at": self.evaluated_at.isoformat(),
            "policy_hash": self.policy_hash,
            "explanation": self.explain(),
        }


@dataclass(frozen=True, slots=True)
class IntentMandate:
    """What the user authorized the system to accomplish.

    Unspecified fields stay ``None``.  The engine reads ``None`` as "the user
    said nothing about this", which is never the same as "anything goes".
    """

    mandate_id: str
    user_id: str
    raw_utterance: str
    """The user's own words, kept verbatim as the consent record."""

    product_query: str
    max_amount: Money | None = None
    preferred_amount: Money | None = None
    quantity: int = 1
    currency: str = "INR"
    max_delivery_days: int | None = None
    required_condition: str | None = None
    """e.g. ``"new"`` -- refurbished is not a silent substitute."""

    require_return_policy: bool = False
    require_warranty: bool = False
    require_verified_merchant: bool = True
    allowed_categories: tuple[str, ...] = ()
    allowed_merchants: tuple[str, ...] = ()
    blocked_merchants: tuple[str, ...] = ()
    autonomy: AutonomyLevel = AutonomyLevel.HUMAN_PRESENT
    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    interpreted_by: str | None = None
    """Which model proposed this reading, for audit.  Never grants authority."""

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        raw_utterance: str,
        product_query: str,
        valid_for: timedelta | None = None,
        **kwargs: Any,
    ) -> IntentMandate:
        expires = utcnow() + valid_for if valid_for else None
        return cls(
            mandate_id=f"mandate-{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            raw_utterance=raw_utterance,
            product_query=product_query,
            expires_at=expires,
            **kwargs,
        )

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return self.expires_at is not None and (now or utcnow()) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "user_id": self.user_id,
            "raw_utterance": self.raw_utterance,
            "product_query": self.product_query,
            "max_amount": self.max_amount.to_dict() if self.max_amount else None,
            "preferred_amount": (
                self.preferred_amount.to_dict() if self.preferred_amount else None
            ),
            "quantity": self.quantity,
            "currency": self.currency,
            "max_delivery_days": self.max_delivery_days,
            "required_condition": self.required_condition,
            "require_return_policy": self.require_return_policy,
            "require_warranty": self.require_warranty,
            "require_verified_merchant": self.require_verified_merchant,
            "allowed_categories": list(self.allowed_categories),
            "allowed_merchants": list(self.allowed_merchants),
            "blocked_merchants": list(self.blocked_merchants),
            "autonomy": str(self.autonomy),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "interpreted_by": self.interpreted_by,
        }


@dataclass(frozen=True, slots=True)
class Policy:
    """Machine-readable limits, evaluated deterministically.

    Thresholds are inclusive ceilings: ``max_amount`` is the largest amount
    that may be spent, not the first amount that is refused.
    """

    max_amount: Money | None = None
    review_above: Money | None = None
    """Amounts above this need a human even when inside ``max_amount``."""

    allowed_categories: tuple[str, ...] = ()
    allowed_merchants: tuple[str, ...] = ()
    blocked_merchants: tuple[str, ...] = ()
    max_delivery_days: int | None = None
    require_verified_merchant: bool = True
    require_return_policy: bool = False
    autonomous_purchase: bool = False
    max_evidence_age: timedelta = timedelta(minutes=15)
    """Price evidence older than this is stale and cannot justify a purchase."""

    allow_sandbox_evidence: bool = False
    """Must be set explicitly for a sandbox run.  Never true in production."""

    def fingerprint(self) -> str:
        return content_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_amount": self.max_amount.to_dict() if self.max_amount else None,
            "review_above": self.review_above.to_dict() if self.review_above else None,
            "allowed_categories": list(self.allowed_categories),
            "allowed_merchants": list(self.allowed_merchants),
            "blocked_merchants": list(self.blocked_merchants),
            "max_delivery_days": self.max_delivery_days,
            "require_verified_merchant": self.require_verified_merchant,
            "require_return_policy": self.require_return_policy,
            "autonomous_purchase": self.autonomous_purchase,
            "max_evidence_age_seconds": int(self.max_evidence_age.total_seconds()),
            "allow_sandbox_evidence": self.allow_sandbox_evidence,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Policy:
        """Parse the machine-readable shape.  Unknown keys raise, never ignored."""
        known = {
            "max_amount",
            "review_above",
            "allowed_categories",
            "allowed_merchants",
            "blocked_merchants",
            "max_delivery_days",
            "require_verified_merchant",
            "require_return_policy",
            "autonomous_purchase",
            "max_evidence_age_seconds",
            "allow_sandbox_evidence",
        }
        unknown = set(raw) - known
        if unknown:
            raise ValueError(
                f"unknown policy keys: {sorted(unknown)}; a typo must not silently "
                "widen or narrow a limit"
            )
        age = raw.get("max_evidence_age_seconds")
        return cls(
            max_amount=(
                Money.from_dict(raw["max_amount"]) if raw.get("max_amount") else None
            ),
            review_above=(
                Money.from_dict(raw["review_above"])
                if raw.get("review_above")
                else None
            ),
            allowed_categories=tuple(raw.get("allowed_categories") or ()),
            allowed_merchants=tuple(raw.get("allowed_merchants") or ()),
            blocked_merchants=tuple(raw.get("blocked_merchants") or ()),
            max_delivery_days=raw.get("max_delivery_days"),
            require_verified_merchant=bool(raw.get("require_verified_merchant", True)),
            require_return_policy=bool(raw.get("require_return_policy", False)),
            autonomous_purchase=bool(raw.get("autonomous_purchase", False)),
            max_evidence_age=(
                timedelta(seconds=int(age))
                if age is not None
                else timedelta(minutes=15)
            ),
            allow_sandbox_evidence=bool(raw.get("allow_sandbox_evidence", False)),
        )

    @classmethod
    def from_mandate(cls, mandate: IntentMandate, **overrides: Any) -> Policy:
        """Derive the enforceable policy implied by a mandate.

        The mandate is what the user said; the policy is what the engine will
        enforce.  Deriving one from the other keeps them from drifting apart.
        """
        base = cls(
            max_amount=mandate.max_amount,
            allowed_categories=mandate.allowed_categories,
            allowed_merchants=mandate.allowed_merchants,
            blocked_merchants=mandate.blocked_merchants,
            max_delivery_days=mandate.max_delivery_days,
            require_verified_merchant=mandate.require_verified_merchant,
            require_return_policy=mandate.require_return_policy,
            autonomous_purchase=mandate.autonomy is AutonomyLevel.AUTONOMOUS,
        )
        return replace(base, **overrides) if overrides else base


@dataclass(frozen=True, slots=True)
class Candidate:
    """What the engine is being asked to approve.

    Deliberately flat and dumb: every field is either a checked value or an
    :class:`Observation` carrying its own provenance.  Nothing here is
    inferred.
    """

    amount: Money
    merchant_id: str
    merchant_verified: bool
    category: str | None = None
    delivery_days: int | None = None
    has_return_policy: bool | None = None
    condition: str | None = None
    price_observation: Observation | None = None
    risk_score: float | None = None
    """0.0-1.0, advisory only.  A score alone never authorizes or blocks."""


class PolicyEngine:
    """Deterministic evaluation of a candidate against a policy and mandate.

    Every rule appends a :class:`Reason`.  The final outcome is the most
    severe one seen -- BLOCK beats REVIEW beats ALLOW -- so adding a rule can
    never accidentally loosen the engine.
    """

    def evaluate(
        self,
        candidate: Candidate,
        policy: Policy,
        mandate: IntentMandate | None = None,
        *,
        now: datetime | None = None,
    ) -> Decision:
        moment = now or utcnow()
        reasons: list[Reason] = []

        self._check_mandate(reasons, mandate, moment)
        self._check_amount(reasons, candidate, policy)
        self._check_merchant(reasons, candidate, policy)
        self._check_category(reasons, candidate, policy)
        self._check_delivery(reasons, candidate, policy)
        self._check_return_policy(reasons, candidate, policy)
        self._check_condition(reasons, candidate, mandate)
        self._check_evidence(reasons, candidate, policy, moment)
        self._check_risk(reasons, candidate)

        return Decision(
            outcome=self._worst(reasons),
            reasons=tuple(reasons),
            evaluated_at=moment,
            policy_hash=policy.fingerprint(),
        )

    # --- individual rules ----------------------------------------------

    @staticmethod
    def _check_mandate(
        reasons: list[Reason], mandate: IntentMandate | None, now: datetime
    ) -> None:
        if mandate is None:
            return
        if mandate.is_expired(now=now):
            when = mandate.expires_at.isoformat() if mandate.expires_at else "?"
            reasons.append(
                Reason(
                    code="MANDATE_EXPIRED",
                    detail=f"the user's authorization expired at {when}",
                    outcome=Outcome.BLOCK,
                    evidence=(mandate.mandate_id,),
                )
            )

    @staticmethod
    def _check_amount(
        reasons: list[Reason], candidate: Candidate, policy: Policy
    ) -> None:
        ceiling = policy.max_amount
        if ceiling is None:
            # Silence is not consent.  With no stated ceiling there is no
            # authority to spend, so this needs a human rather than a guess.
            reasons.append(
                Reason(
                    code="NO_AMOUNT_CEILING",
                    detail=(
                        "no maximum amount was authorized; an unstated limit is "
                        "not an unlimited one"
                    ),
                    outcome=Outcome.REVIEW,
                )
            )
            return
        if candidate.amount.currency != ceiling.currency:
            reasons.append(
                Reason(
                    code="CURRENCY_MISMATCH",
                    detail=(
                        f"candidate is in {candidate.amount.currency} but the "
                        f"authorization is in {ceiling.currency}"
                    ),
                    outcome=Outcome.BLOCK,
                )
            )
            return
        if candidate.amount > ceiling:
            reasons.append(
                Reason(
                    code="AMOUNT_ABOVE_MAX",
                    detail=f"{candidate.amount} exceeds the authorized {ceiling}",
                    outcome=Outcome.BLOCK,
                )
            )
        else:
            reasons.append(
                Reason(
                    code="AMOUNT_WITHIN_MAX",
                    detail=f"{candidate.amount} is within the authorized {ceiling}",
                    outcome=Outcome.ALLOW,
                )
            )
        if (
            policy.review_above is not None
            and candidate.amount.currency == policy.review_above.currency
            and candidate.amount > policy.review_above
        ):
            reasons.append(
                Reason(
                    code="AMOUNT_NEEDS_CONFIRMATION",
                    detail=(
                        f"{candidate.amount} is above the {policy.review_above} "
                        "confirmation threshold"
                    ),
                    outcome=Outcome.REVIEW,
                )
            )

    @staticmethod
    def _check_merchant(
        reasons: list[Reason], candidate: Candidate, policy: Policy
    ) -> None:
        if candidate.merchant_id in policy.blocked_merchants:
            reasons.append(
                Reason(
                    code="MERCHANT_BLOCKED",
                    detail=f"{candidate.merchant_id} is on the blocklist",
                    outcome=Outcome.BLOCK,
                    evidence=(candidate.merchant_id,),
                )
            )
            return
        if (
            policy.allowed_merchants
            and candidate.merchant_id not in policy.allowed_merchants
        ):
            reasons.append(
                Reason(
                    code="MERCHANT_NOT_ALLOWLISTED",
                    detail=(
                        f"{candidate.merchant_id} is not among the "
                        f"{len(policy.allowed_merchants)} allowed merchants"
                    ),
                    outcome=Outcome.BLOCK,
                    evidence=(candidate.merchant_id,),
                )
            )
            return
        if policy.require_verified_merchant and not candidate.merchant_verified:
            reasons.append(
                Reason(
                    code="MERCHANT_UNVERIFIED",
                    detail=(
                        f"{candidate.merchant_id} could not be verified and the "
                        "policy requires a verified merchant"
                    ),
                    outcome=Outcome.REVIEW,
                    evidence=(candidate.merchant_id,),
                )
            )

    @staticmethod
    def _check_category(
        reasons: list[Reason], candidate: Candidate, policy: Policy
    ) -> None:
        if not policy.allowed_categories:
            return
        if candidate.category is None:
            reasons.append(
                Reason(
                    code="CATEGORY_UNKNOWN",
                    detail="the policy restricts categories but this offer has none",
                    outcome=Outcome.REVIEW,
                )
            )
        elif candidate.category not in policy.allowed_categories:
            reasons.append(
                Reason(
                    code="CATEGORY_NOT_ALLOWED",
                    detail=(
                        f"category {candidate.category!r} is not in "
                        f"{list(policy.allowed_categories)}"
                    ),
                    outcome=Outcome.BLOCK,
                )
            )

    @staticmethod
    def _check_delivery(
        reasons: list[Reason], candidate: Candidate, policy: Policy
    ) -> None:
        limit = policy.max_delivery_days
        if limit is None:
            return
        if candidate.delivery_days is None:
            reasons.append(
                Reason(
                    code="DELIVERY_UNKNOWN",
                    detail=(
                        f"no delivery estimate, but the user requires <= {limit} days"
                    ),
                    outcome=Outcome.REVIEW,
                )
            )
        elif candidate.delivery_days > limit:
            reasons.append(
                Reason(
                    code="DELIVERY_TOO_SLOW",
                    detail=(
                        f"{candidate.delivery_days} days exceeds the "
                        f"{limit}-day requirement"
                    ),
                    outcome=Outcome.BLOCK,
                )
            )

    @staticmethod
    def _check_return_policy(
        reasons: list[Reason], candidate: Candidate, policy: Policy
    ) -> None:
        if not policy.require_return_policy:
            return
        if candidate.has_return_policy is None:
            reasons.append(
                Reason(
                    code="RETURN_POLICY_UNKNOWN",
                    detail="a return policy is required but none could be confirmed",
                    outcome=Outcome.REVIEW,
                )
            )
        elif not candidate.has_return_policy:
            reasons.append(
                Reason(
                    code="NO_RETURN_POLICY",
                    detail="the merchant offers no return policy",
                    outcome=Outcome.BLOCK,
                )
            )

    @staticmethod
    def _check_condition(
        reasons: list[Reason], candidate: Candidate, mandate: IntentMandate | None
    ) -> None:
        if mandate is None or mandate.required_condition is None:
            return
        want = mandate.required_condition
        if candidate.condition is None:
            reasons.append(
                Reason(
                    code="CONDITION_UNKNOWN",
                    detail=f"the user required {want!r}; item condition is unknown",
                    outcome=Outcome.REVIEW,
                )
            )
        elif candidate.condition != want:
            reasons.append(
                Reason(
                    code="CONDITION_MISMATCH",
                    detail=(
                        f"the user required {want!r} but this is "
                        f"{candidate.condition!r}"
                    ),
                    outcome=Outcome.BLOCK,
                )
            )

    @staticmethod
    def _check_evidence(
        reasons: list[Reason], candidate: Candidate, policy: Policy, now: datetime
    ) -> None:
        obs = candidate.price_observation
        if obs is None:
            reasons.append(
                Reason(
                    code="PRICE_EVIDENCE_MISSING",
                    detail="no price observation backs this amount",
                    outcome=Outcome.BLOCK,
                )
            )
            return
        aged = obs.aged(policy.max_evidence_age, now=now)
        source = aged.provenance.source

        # Whatever the evidence class, an amount that contradicts the observed
        # price is never allowed through.  This runs before the class branches
        # below because each of those returns early, and a sandbox or stale
        # observation must not become a way to skip the comparison.
        observed: Money | None = None
        if isinstance(aged.value, Money):
            observed = aged.value
        elif isinstance(aged.value, dict) and "minor" in aged.value:
            observed = Money.from_dict(aged.value)
        if observed is not None and observed != candidate.amount:
            reasons.append(
                Reason(
                    code="AMOUNT_NOT_EVIDENCED",
                    detail=(
                        f"the candidate amount {candidate.amount} does not match "
                        f"the observed price {observed}"
                    ),
                    outcome=Outcome.BLOCK,
                    evidence=(source,),
                )
            )
            return

        if aged.evidence_class is EvidenceClass.SANDBOX:
            if policy.allow_sandbox_evidence:
                reasons.append(
                    Reason(
                        code="SANDBOX_EVIDENCE_ACCEPTED",
                        detail=(
                            "price comes from a sandbox adapter; allowed only "
                            "because this policy opts in. Not a real-world price."
                        ),
                        outcome=Outcome.REVIEW,
                        evidence=(source,),
                    )
                )
            else:
                reasons.append(
                    Reason(
                        code="SANDBOX_EVIDENCE_REFUSED",
                        detail=(
                            "price comes from a sandbox adapter and this policy "
                            "does not permit sandbox evidence"
                        ),
                        outcome=Outcome.BLOCK,
                        evidence=(source,),
                    )
                )
            return

        if aged.evidence_class is EvidenceClass.STALE:
            reasons.append(
                Reason(
                    code="PRICE_EVIDENCE_STALE",
                    detail=(
                        f"price was observed {aged.provenance.age(now=now)} ago, "
                        f"past the {policy.max_evidence_age} freshness window"
                    ),
                    outcome=Outcome.REVIEW,
                    evidence=(source,),
                )
            )
            return

        if aged.evidence_class in (
            EvidenceClass.UNAVAILABLE,
            EvidenceClass.UNKNOWN,
            EvidenceClass.CONFLICTING,
        ):
            reasons.append(
                Reason(
                    code=f"PRICE_EVIDENCE_{aged.evidence_class}",
                    detail=aged.note or f"price evidence is {aged.evidence_class}",
                    outcome=Outcome.BLOCK,
                    evidence=(source,),
                )
            )
            return

        # Decision grade, and the amount already matched the observation above.
        reasons.append(
            Reason(
                code="PRICE_EVIDENCED",
                detail=f"price confirmed by {source}",
                outcome=Outcome.ALLOW,
                evidence=(source,),
            )
        )

    @staticmethod
    def _check_risk(reasons: list[Reason], candidate: Candidate) -> None:
        score = candidate.risk_score
        if score is None:
            return
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"risk_score must be in [0,1], got {score}")
        # A model's score may raise friction but never lower it, and it can
        # never be the sole ground for an irreversible action.
        if score >= 0.8:
            reasons.append(
                Reason(
                    code="RISK_HIGH",
                    detail=(
                        f"advisory risk score {score:.2f} is high; a human must decide"
                    ),
                    outcome=Outcome.REVIEW,
                )
            )
        elif score >= 0.5:
            reasons.append(
                Reason(
                    code="RISK_ELEVATED",
                    detail=f"advisory risk score {score:.2f} is elevated",
                    outcome=Outcome.REVIEW,
                )
            )

    @staticmethod
    def _worst(reasons: list[Reason]) -> Outcome:
        if any(r.outcome is Outcome.BLOCK for r in reasons):
            return Outcome.BLOCK
        if any(r.outcome is Outcome.REVIEW for r in reasons):
            return Outcome.REVIEW
        return Outcome.ALLOW
