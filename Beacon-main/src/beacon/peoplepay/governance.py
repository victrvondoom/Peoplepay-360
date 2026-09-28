"""Cross-cutting controls for risk, cost, consent and community privacy.

These controls are deterministic and sit outside the model.  They turn four
product promises into executable rules: autonomy shrinks as risk grows, a
transaction cannot spend unlimited compute, consent is purpose-bound and
revocable, and community statistics disappear when a cohort is too small.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from beacon.assurance import EvidenceClass, Money, content_hash, utcnow
from beacon.peoplepay.authority import TransactionType

if TYPE_CHECKING:
    from datetime import date, datetime

__all__ = [
    "BudgetExceeded",
    "CommunityAggregator",
    "ConsentLedger",
    "ConsentPurpose",
    "ConsentReceipt",
    "CostBudget",
    "ExperienceContribution",
    "RiskAssessment",
    "RiskDisposition",
    "RiskEngine",
    "UsageMeter",
]


class RiskDisposition(StrEnum):
    """The maximum autonomy allowed after deterministic evaluation."""

    ALLOW = "ALLOW"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    REQUIRE_SPECIALIST = "REQUIRE_SPECIALIST"
    BLOCK = "BLOCK"


_DISPOSITION_ORDER = {
    RiskDisposition.ALLOW: 0,
    RiskDisposition.REQUIRE_CONFIRMATION: 1,
    RiskDisposition.REQUIRE_SPECIALIST: 2,
    RiskDisposition.BLOCK: 3,
}


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    disposition: RiskDisposition
    reasons: tuple[str, ...]
    evaluated_at: datetime = field(default_factory=utcnow)

    @property
    def may_execute(self) -> bool:
        return self.disposition in (
            RiskDisposition.ALLOW,
            RiskDisposition.REQUIRE_CONFIRMATION,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": str(self.disposition),
            "reasons": list(self.reasons),
            "may_execute": self.may_execute,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


class RiskEngine:
    """Reduce autonomy as consequence, uncertainty and value increase."""

    def __init__(self, *, specialist_threshold: Money) -> None:
        if specialist_threshold.minor <= 0:
            raise ValueError("specialist_threshold must be positive")
        self.specialist_threshold = specialist_threshold

    def assess(
        self,
        *,
        transaction_type: TransactionType,
        amount: Money | None,
        evidence_classes: tuple[EvidenceClass, ...] = (),
        consequential: bool,
        legal_interpretation: bool = False,
        credential_sharing: bool = False,
    ) -> RiskAssessment:
        disposition = RiskDisposition.ALLOW
        reasons: list[str] = []

        def raise_to(target: RiskDisposition, reason: str) -> None:
            nonlocal disposition
            if _DISPOSITION_ORDER[target] > _DISPOSITION_ORDER[disposition]:
                disposition = target
            reasons.append(reason)

        blocking = {
            EvidenceClass.CONFLICTING,
            EvidenceClass.UNAVAILABLE,
            EvidenceClass.UNKNOWN,
            EvidenceClass.SANDBOX,
            EvidenceClass.STALE,
        }
        bad = sorted({str(item) for item in evidence_classes if item in blocking})
        if consequential and bad:
            raise_to(
                RiskDisposition.BLOCK,
                "consequential action has non-decision-grade evidence: "
                + ", ".join(bad),
            )
        elif EvidenceClass.UNVERIFIED in evidence_classes:
            raise_to(
                RiskDisposition.REQUIRE_CONFIRMATION,
                "one or more claims are unverified",
            )

        if consequential:
            raise_to(
                RiskDisposition.REQUIRE_CONFIRMATION,
                "the action creates an external side effect",
            )
        if credential_sharing:
            raise_to(
                RiskDisposition.REQUIRE_CONFIRMATION,
                "the action shares credentials with an external provider",
            )
        if legal_interpretation or transaction_type is TransactionType.PROPERTY:
            raise_to(
                RiskDisposition.REQUIRE_SPECIALIST,
                "property or legal interpretation requires qualified review",
            )
        if amount is not None:
            if amount.currency != self.specialist_threshold.currency:
                raise_to(
                    RiskDisposition.REQUIRE_SPECIALIST,
                    "value threshold cannot be compared across currencies",
                )
            elif amount >= self.specialist_threshold:
                raise_to(
                    RiskDisposition.REQUIRE_SPECIALIST,
                    "transaction meets the specialist-review value threshold",
                )

        return RiskAssessment(
            disposition=disposition,
            reasons=tuple(dict.fromkeys(reasons)) or ("no elevated risk signal",),
        )


class BudgetExceeded(RuntimeError):
    """A transaction attempted to consume more compute than authorized."""


@dataclass(frozen=True, slots=True)
class CostBudget:
    """Hard economic limits for one transaction."""

    max_provider_cost: Money
    max_model_calls: int
    max_search_calls: int
    max_external_calls: int
    max_latency_ms: int

    def __post_init__(self) -> None:
        if self.max_provider_cost.minor < 0:
            raise ValueError("max_provider_cost cannot be negative")
        values = (
            self.max_model_calls,
            self.max_search_calls,
            self.max_external_calls,
            self.max_latency_ms,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) for value in values
        ):
            raise TypeError("budget counters must be integers")
        if any(value < 0 for value in values):
            raise ValueError("budget counters cannot be negative")


@dataclass(slots=True)
class UsageMeter:
    """Claim resource use before making an external or model call."""

    budget: CostBudget
    provider_cost: Money = field(init=False)
    model_calls: int = 0
    search_calls: int = 0
    external_calls: int = 0
    latency_ms: int = 0

    def __post_init__(self) -> None:
        self.provider_cost = Money.zero(self.budget.max_provider_cost.currency)

    def consume(
        self,
        *,
        provider_cost: Money | None = None,
        model_calls: int = 0,
        search_calls: int = 0,
        external_calls: int = 0,
        latency_ms: int = 0,
    ) -> None:
        increments = (model_calls, search_calls, external_calls, latency_ms)
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in increments
        ):
            raise TypeError("usage increments must be integers")
        if any(value < 0 for value in increments):
            raise ValueError("usage increments cannot be negative")

        next_cost = self.provider_cost + (
            provider_cost or Money.zero(self.provider_cost.currency)
        )
        proposed = {
            "provider cost": (next_cost.minor, self.budget.max_provider_cost.minor),
            "model calls": (
                self.model_calls + model_calls,
                self.budget.max_model_calls,
            ),
            "search calls": (
                self.search_calls + search_calls,
                self.budget.max_search_calls,
            ),
            "external calls": (
                self.external_calls + external_calls,
                self.budget.max_external_calls,
            ),
            "latency": (self.latency_ms + latency_ms, self.budget.max_latency_ms),
        }
        exceeded = [name for name, (used, limit) in proposed.items() if used > limit]
        if exceeded:
            raise BudgetExceeded(f"transaction budget exceeded: {', '.join(exceeded)}")

        self.provider_cost = next_cost
        self.model_calls += model_calls
        self.search_calls += search_calls
        self.external_calls += external_calls
        self.latency_ms += latency_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_cost": self.provider_cost.to_dict(),
            "model_calls": self.model_calls,
            "search_calls": self.search_calls,
            "external_calls": self.external_calls,
            "latency_ms": self.latency_ms,
        }


class ConsentPurpose(StrEnum):
    MEMORY = "MEMORY"
    EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"
    COMMUNITY_REVIEW = "COMMUNITY_REVIEW"
    SHARE_PRICE = "SHARE_PRICE"
    SHARE_PURCHASE_DATE = "SHARE_PURCHASE_DATE"
    LEGAL_HANDOFF = "LEGAL_HANDOFF"


@dataclass(frozen=True, slots=True)
class ConsentReceipt:
    consent_id: str
    user_id: str
    purpose: ConsentPurpose
    fields: tuple[str, ...]
    notice_hash: str
    confirmation_hash: str
    granted_at: datetime
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "consent_id": self.consent_id,
            "user_id": self.user_id,
            "purpose": str(self.purpose),
            "fields": list(self.fields),
            "notice_hash": self.notice_hash,
            "confirmation_hash": self.confirmation_hash,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass(frozen=True, slots=True)
class _Revocation:
    consent_id: str
    revoked_at: datetime
    reason: str


class ConsentLedger:
    """Append-only, purpose-bound consent with equally easy withdrawal."""

    def __init__(self) -> None:
        self._grants: list[ConsentReceipt] = []
        self._revocations: list[_Revocation] = []

    def grant(
        self,
        *,
        user_id: str,
        purpose: ConsentPurpose,
        fields: tuple[str, ...],
        notice: str,
        raw_confirmation: str,
        expires_at: datetime | None = None,
    ) -> ConsentReceipt:
        if not user_id.strip() or not notice.strip() or not raw_confirmation.strip():
            raise ValueError("user, notice and explicit confirmation are required")
        normalized = tuple(sorted(set(fields)))
        if not normalized or any(not item.strip() for item in normalized):
            raise ValueError("consent must name at least one non-empty field")
        now = utcnow()
        if expires_at is not None and expires_at <= now:
            raise ValueError("consent expiry must be in the future")
        receipt = ConsentReceipt(
            consent_id=f"consent-{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            purpose=purpose,
            fields=normalized,
            notice_hash=content_hash(notice),
            confirmation_hash=content_hash(raw_confirmation),
            granted_at=now,
            expires_at=expires_at,
        )
        self._grants.append(receipt)
        return receipt

    def revoke(self, consent_id: str, *, reason: str = "user withdrew consent") -> None:
        if not any(item.consent_id == consent_id for item in self._grants):
            raise KeyError(consent_id)
        if any(item.consent_id == consent_id for item in self._revocations):
            return
        self._revocations.append(
            _Revocation(consent_id=consent_id, revoked_at=utcnow(), reason=reason)
        )

    def allows(
        self,
        *,
        user_id: str,
        purpose: ConsentPurpose,
        fields: tuple[str, ...],
        now: datetime | None = None,
    ) -> bool:
        revoked = {item.consent_id for item in self._revocations}
        required = set(fields)
        at = now or utcnow()
        return any(
            receipt.user_id == user_id
            and receipt.purpose is purpose
            and required.issubset(receipt.fields)
            and receipt.consent_id not in revoked
            and (receipt.expires_at is None or at < receipt.expires_at)
            for receipt in reversed(self._grants)
        )

    def history(self, user_id: str) -> tuple[dict[str, Any], ...]:
        revoked = {item.consent_id: item for item in self._revocations}
        return tuple(
            {
                **receipt.to_dict(),
                "revoked_at": (
                    revoked[receipt.consent_id].revoked_at.isoformat()
                    if receipt.consent_id in revoked
                    else None
                ),
            }
            for receipt in self._grants
            if receipt.user_id == user_id
        )


@dataclass(frozen=True, slots=True)
class ExperienceContribution:
    """Private input to an aggregate; contributor identity is never returned."""

    contributor_id: str
    product_id: str
    rating: int
    ownership_days: int
    verified_purchase: bool
    price: Money | None = None
    purchased_on: date | None = None

    def __post_init__(self) -> None:
        if not self.contributor_id.strip() or not self.product_id.strip():
            raise ValueError("contributor_id and product_id are required")
        if self.rating not in range(1, 6):
            raise ValueError("rating must be between 1 and 5")
        if self.ownership_days < 0:
            raise ValueError("ownership_days cannot be negative")


class CommunityAggregator:
    """Release only consented statistics from sufficiently large cohorts."""

    def __init__(
        self,
        consents: ConsentLedger,
        *,
        min_cohort: int = 10,
        max_queries_per_product: int = 20,
    ) -> None:
        if min_cohort < 2 or max_queries_per_product < 1:
            raise ValueError("privacy thresholds are too small")
        self.consents = consents
        self.min_cohort = min_cohort
        self.max_queries_per_product = max_queries_per_product
        self._items: list[ExperienceContribution] = []
        self._queries: dict[str, int] = {}

    def contribute(self, item: ExperienceContribution) -> None:
        base_fields = ("rating", "ownership_days", "verified_purchase")
        if not self.consents.allows(
            user_id=item.contributor_id,
            purpose=ConsentPurpose.COMMUNITY_REVIEW,
            fields=base_fields,
        ):
            raise PermissionError("community contribution lacks active consent")
        if item.price is not None and not self.consents.allows(
            user_id=item.contributor_id,
            purpose=ConsentPurpose.SHARE_PRICE,
            fields=("price",),
        ):
            raise PermissionError("price sharing lacks separate active consent")
        if item.purchased_on is not None and not self.consents.allows(
            user_id=item.contributor_id,
            purpose=ConsentPurpose.SHARE_PURCHASE_DATE,
            fields=("purchased_on",),
        ):
            raise PermissionError("purchase-date sharing lacks separate active consent")
        self._items.append(item)

    def aggregate(self, product_id: str) -> dict[str, Any]:
        count = self._queries.get(product_id, 0) + 1
        self._queries[product_id] = count
        if count > self.max_queries_per_product:
            return {"product_id": product_id, "status": "PRIVACY_BUDGET_EXHAUSTED"}

        latest_by_user: dict[str, ExperienceContribution] = {}
        for item in self._items:
            if item.product_id == product_id and self.consents.allows(
                user_id=item.contributor_id,
                purpose=ConsentPurpose.COMMUNITY_REVIEW,
                fields=("rating", "ownership_days", "verified_purchase"),
            ):
                latest_by_user[item.contributor_id] = item
        cohort = list(latest_by_user.values())
        if len(cohort) < self.min_cohort:
            return {
                "product_id": product_id,
                "status": "SUPPRESSED_SMALL_COHORT",
                "minimum_required": self.min_cohort,
            }

        average = (
            Decimal(sum(item.rating for item in cohort)) / Decimal(len(cohort))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        result: dict[str, Any] = {
            "product_id": product_id,
            "status": "AVAILABLE",
            "contributors": len(cohort),
            "average_rating": str(average),
            "verified_purchase_count": sum(item.verified_purchase for item in cohort),
            "minimum_ownership_days": min(item.ownership_days for item in cohort),
        }

        prices = [
            item.price
            for item in cohort
            if item.price is not None
            and self.consents.allows(
                user_id=item.contributor_id,
                purpose=ConsentPurpose.SHARE_PRICE,
                fields=("price",),
            )
        ]
        if len(prices) >= self.min_cohort:
            currencies = {item.currency for item in prices}
            if len(currencies) == 1:
                currency = prices[0].currency
                total_minor = sum(item.minor for item in prices)
                result["average_price"] = Money(
                    total_minor // len(prices), currency
                ).to_dict()
        return result
