"""The transaction contract, scoped authorization, and bound mandates.

The contract is the heart of the system.  It is the written form of *exactly*
what the user authorized, and the only thing execution is allowed to check
itself against.  Drift -- a price that moved, a merchant that swapped, a
product that changed variant between evaluation and checkout -- is caught by
:meth:`TransactionContract.check`, which compares the live cart against the
frozen terms and names the violation rather than shrugging.

The mandate chain follows the separation the Agent Payments Protocol draws,
with abstractions of our own rather than a copy of anyone's implementation:

    IntentMandate    what the user wants (see :mod:`beacon.assurance.policy`)
        |
    CheckoutMandate  the exact cart: product, merchant, amount, quantity
        |
    PaymentMandate   authority to pay *for that checkout and no other*

A :class:`PaymentMandate` carries the ``checkout_hash`` of the checkout it was
minted for.  Replaying it against a different cart fails
:meth:`PaymentMandate.covers`, which is what stops a captured authorization
from being spent somewhere else.  This mirrors the ``params_hash`` binding
already used by Beacon's AWS approval ledger in :mod:`beacon.approvals` --
the same principle, applied to money.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from beacon.assurance.evidence import content_hash, utcnow
from beacon.assurance.money import Money
from beacon.assurance.policy import AutonomyLevel, IntentMandate, Policy

__all__ = [
    "Authorization",
    "CheckoutMandate",
    "ContractViolation",
    "ObservedCheckout",
    "PaymentMandate",
    "TransactionContract",
    "ViolationKind",
]


class ViolationKind(StrEnum):
    """Every way reality can differ from what was authorized."""

    PRICE_ABOVE_MAX = "PRICE_ABOVE_MAX"
    PRICE_CHANGED = "PRICE_CHANGED"
    MERCHANT_CHANGED = "MERCHANT_CHANGED"
    PRODUCT_CHANGED = "PRODUCT_CHANGED"
    QUANTITY_CHANGED = "QUANTITY_CHANGED"
    CURRENCY_CHANGED = "CURRENCY_CHANGED"
    DELIVERY_TOO_SLOW = "DELIVERY_TOO_SLOW"
    PAYMENT_METHOD_CHANGED = "PAYMENT_METHOD_CHANGED"
    CONTRACT_EXPIRED = "CONTRACT_EXPIRED"
    FEES_UNDISCLOSED = "FEES_UNDISCLOSED"


# Which violations mean "ask the user again" versus "stop entirely".  A price
# that moved can be re-authorized; a merchant that silently swapped cannot be
# waved through by the same agent that failed to notice.
_RE_AUTHORIZABLE: frozenset[ViolationKind] = frozenset(
    {
        ViolationKind.PRICE_CHANGED,
        ViolationKind.PRICE_ABOVE_MAX,
        ViolationKind.DELIVERY_TOO_SLOW,
        ViolationKind.QUANTITY_CHANGED,
        ViolationKind.FEES_UNDISCLOSED,
        ViolationKind.CONTRACT_EXPIRED,
    }
)


def _plain(value: Any) -> Any:
    """Render Money and datetimes for serialization without losing precision."""
    if isinstance(value, Money):
        return value.to_dict()
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True, slots=True)
class ContractViolation:
    """A named, evidenced difference between the contract and reality."""

    kind: ViolationKind
    expected: Any
    observed: Any
    detail: str

    @property
    def is_re_authorizable(self) -> bool:
        """True when a fresh human authorization could rescue this."""
        return self.kind in _RE_AUTHORIZABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "expected": _plain(self.expected),
            "observed": _plain(self.observed),
            "detail": self.detail,
            "re_authorizable": self.is_re_authorizable,
        }


@dataclass(frozen=True, slots=True)
class ObservedCheckout:
    """What the cart *actually* says, right before money moves.

    Built from the execution surface (an API response or a scraped cart), not
    from the model's recollection of what it selected.
    """

    product_id: str
    merchant_id: str
    unit_amount: Money
    quantity: int
    total_amount: Money
    currency: str
    delivery_days: int | None = None
    payment_method_id: str | None = None
    fees: Money | None = None
    observed_at: datetime = field(default_factory=utcnow)

    def checkout_hash(self) -> str:
        """Identity of this exact cart, for binding a payment to it."""
        return content_hash(
            {
                "product_id": self.product_id,
                "merchant_id": self.merchant_id,
                "unit_amount": self.unit_amount.to_dict(),
                "quantity": self.quantity,
                "total_amount": self.total_amount.to_dict(),
                "currency": self.currency,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "merchant_id": self.merchant_id,
            "unit_amount": self.unit_amount.to_dict(),
            "quantity": self.quantity,
            "total_amount": self.total_amount.to_dict(),
            "currency": self.currency,
            "delivery_days": self.delivery_days,
            "payment_method_id": self.payment_method_id,
            "fees": self.fees.to_dict() if self.fees else None,
            "observed_at": self.observed_at.isoformat(),
            "checkout_hash": self.checkout_hash(),
        }


@dataclass(frozen=True, slots=True)
class TransactionContract:
    """The frozen terms.  Execution is legal only while reality matches these.

    ``max_amount`` is a ceiling on the total, and ``expected_amount`` is what
    we were quoted.  Both matter: a cart may come in under the ceiling and
    still be a different price than the one the user saw, which is a
    ``PRICE_CHANGED`` the user deserves to hear about.
    """

    contract_id: str
    transaction_id: str
    mandate_id: str
    user_id: str

    product_id: str
    merchant_id: str
    expected_amount: Money
    max_amount: Money
    currency: str
    quantity: int = 1

    max_delivery_days: int | None = None
    allowed_payment_methods: tuple[str, ...] = ()
    price_tolerance: Money | None = None
    """Movement at or below this is tolerated without re-authorization."""

    require_return_policy: bool = False
    autonomy: AutonomyLevel = AutonomyLevel.HUMAN_PRESENT
    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    policy_hash: str = ""
    sandbox: bool = False
    """True when any input came from a sandbox adapter.  Propagates to receipts."""

    @classmethod
    def create(
        cls,
        *,
        transaction_id: str,
        mandate: IntentMandate,
        policy: Policy,
        product_id: str,
        merchant_id: str,
        expected_amount: Money,
        quantity: int = 1,
        valid_for: timedelta = timedelta(minutes=15),
        max_delivery_days: int | None = None,
        allowed_payment_methods: tuple[str, ...] = (),
        price_tolerance: Money | None = None,
        sandbox: bool = False,
    ) -> TransactionContract:
        """Freeze the terms.  The ceiling comes from the policy, never higher.

        If the user authorized no ceiling, the expected amount becomes the
        ceiling: we will not invent headroom the user never granted.
        """
        ceiling = policy.max_amount or expected_amount
        if expected_amount > ceiling:
            raise ValueError(
                f"expected amount {expected_amount} already exceeds the authorized "
                f"ceiling {ceiling}; no contract can be written for this"
            )
        return cls(
            contract_id=f"contract-{uuid.uuid4().hex[:12]}",
            transaction_id=transaction_id,
            mandate_id=mandate.mandate_id,
            user_id=mandate.user_id,
            product_id=product_id,
            merchant_id=merchant_id,
            expected_amount=expected_amount,
            max_amount=ceiling,
            currency=expected_amount.currency,
            quantity=quantity,
            max_delivery_days=(
                max_delivery_days
                if max_delivery_days is not None
                else policy.max_delivery_days
            ),
            allowed_payment_methods=allowed_payment_methods,
            price_tolerance=price_tolerance,
            require_return_policy=policy.require_return_policy,
            autonomy=mandate.autonomy,
            expires_at=utcnow() + valid_for,
            policy_hash=policy.fingerprint(),
            sandbox=sandbox,
        )

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return self.expires_at is not None and (now or utcnow()) >= self.expires_at

    def check(
        self, observed: ObservedCheckout, *, now: datetime | None = None
    ) -> tuple[ContractViolation, ...]:
        """Compare the live cart against the frozen terms.

        Returns every violation found, not just the first: a cart that changed
        both merchant and price should report both, so the user sees the whole
        picture in one pass instead of one surprise at a time.
        """
        moment = now or utcnow()
        found: list[ContractViolation] = []

        if self.is_expired(now=moment):
            found.append(
                ContractViolation(
                    kind=ViolationKind.CONTRACT_EXPIRED,
                    expected=self.expires_at,
                    observed=moment,
                    detail=(
                        "the authorization window closed before execution reached "
                        "checkout"
                    ),
                )
            )

        if observed.currency != self.currency:
            found.append(
                ContractViolation(
                    kind=ViolationKind.CURRENCY_CHANGED,
                    expected=self.currency,
                    observed=observed.currency,
                    detail="the cart is priced in a different currency",
                )
            )
            # Amount comparisons are meaningless across currencies.
            return tuple(found)

        if observed.product_id != self.product_id:
            found.append(
                ContractViolation(
                    kind=ViolationKind.PRODUCT_CHANGED,
                    expected=self.product_id,
                    observed=observed.product_id,
                    detail="the cart holds a different product than was authorized",
                )
            )

        if observed.merchant_id != self.merchant_id:
            found.append(
                ContractViolation(
                    kind=ViolationKind.MERCHANT_CHANGED,
                    expected=self.merchant_id,
                    observed=observed.merchant_id,
                    detail="the seller changed between authorization and checkout",
                )
            )

        if observed.quantity != self.quantity:
            found.append(
                ContractViolation(
                    kind=ViolationKind.QUANTITY_CHANGED,
                    expected=self.quantity,
                    observed=observed.quantity,
                    detail="the cart quantity differs from the authorized quantity",
                )
            )

        # The ceiling is absolute.
        if observed.total_amount > self.max_amount:
            found.append(
                ContractViolation(
                    kind=ViolationKind.PRICE_ABOVE_MAX,
                    expected=self.max_amount,
                    observed=observed.total_amount,
                    detail=(
                        f"the checkout total {observed.total_amount} exceeds the "
                        f"authorized maximum {self.max_amount}"
                    ),
                )
            )
        elif observed.total_amount != self.expected_amount:
            # Under the ceiling but not the quoted price.  A tolerance may
            # absorb small movement; anything else the user should hear about,
            # including a drop -- a surprise discount can signal a swapped item.
            drift = observed.total_amount - self.expected_amount
            magnitude = Money(abs(drift.minor), drift.currency)
            tolerated = (
                self.price_tolerance is not None and magnitude <= self.price_tolerance
            )
            if not tolerated:
                direction = "rose" if drift.minor > 0 else "fell"
                found.append(
                    ContractViolation(
                        kind=ViolationKind.PRICE_CHANGED,
                        expected=self.expected_amount,
                        observed=observed.total_amount,
                        detail=(
                            f"the price {direction} by {magnitude} between "
                            "authorization and checkout"
                        ),
                    )
                )

        if (
            self.max_delivery_days is not None
            and observed.delivery_days is not None
            and observed.delivery_days > self.max_delivery_days
        ):
            found.append(
                ContractViolation(
                    kind=ViolationKind.DELIVERY_TOO_SLOW,
                    expected=self.max_delivery_days,
                    observed=observed.delivery_days,
                    detail="the cart's delivery estimate misses the agreed deadline",
                )
            )

        if (
            self.allowed_payment_methods
            and observed.payment_method_id is not None
            and observed.payment_method_id not in self.allowed_payment_methods
        ):
            found.append(
                ContractViolation(
                    kind=ViolationKind.PAYMENT_METHOD_CHANGED,
                    expected=list(self.allowed_payment_methods),
                    observed=observed.payment_method_id,
                    detail=(
                        "checkout would use a payment method that was not authorized"
                    ),
                )
            )

        # Fees are part of the total the user agreed to.  Line items that do
        # not add up to the stated total mean something is hidden.
        if observed.fees is not None and observed.fees.minor > 0:
            implied = observed.unit_amount * observed.quantity + observed.fees
            if implied != observed.total_amount:
                found.append(
                    ContractViolation(
                        kind=ViolationKind.FEES_UNDISCLOSED,
                        expected=observed.total_amount,
                        observed=implied,
                        detail=(
                            "the cart's line items plus fees do not add up to the "
                            "stated total"
                        ),
                    )
                )

        return tuple(found)

    def binding_hash(self) -> str:
        """Stable identity of the authorized terms."""
        return content_hash(
            {
                "product_id": self.product_id,
                "merchant_id": self.merchant_id,
                "max_amount": self.max_amount.to_dict(),
                "quantity": self.quantity,
                "currency": self.currency,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "transaction_id": self.transaction_id,
            "mandate_id": self.mandate_id,
            "user_id": self.user_id,
            "product_id": self.product_id,
            "merchant_id": self.merchant_id,
            "expected_amount": self.expected_amount.to_dict(),
            "max_amount": self.max_amount.to_dict(),
            "currency": self.currency,
            "quantity": self.quantity,
            "max_delivery_days": self.max_delivery_days,
            "allowed_payment_methods": list(self.allowed_payment_methods),
            "price_tolerance": (
                self.price_tolerance.to_dict() if self.price_tolerance else None
            ),
            "require_return_policy": self.require_return_policy,
            "autonomy": str(self.autonomy),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "policy_hash": self.policy_hash,
            "binding_hash": self.binding_hash(),
            "sandbox": self.sandbox,
        }


@dataclass(frozen=True, slots=True)
class Authorization:
    """The user's consent to one contract, scoped and expiring.

    ``transcript_quote`` is the user's own words.  Beacon's voice path already
    checks consent against the raw transcript rather than the model's claim
    that consent was given; the same discipline applies here.
    """

    authorization_id: str
    transaction_id: str
    contract_id: str
    user_id: str
    granted_at: datetime
    expires_at: datetime
    transcript_quote: str
    channel: str
    binding_hash: str
    max_uses: int = 1
    uses: int = 0
    revoked_at: datetime | None = None
    revoked_reason: str = ""

    @classmethod
    def grant(
        cls,
        contract: TransactionContract,
        *,
        transcript_quote: str,
        channel: str,
        valid_for: timedelta = timedelta(minutes=15),
        max_uses: int = 1,
    ) -> Authorization:
        if not transcript_quote.strip():
            raise ValueError(
                "an authorization needs the user's actual words; an empty quote "
                "is not consent"
            )
        now = utcnow()
        return cls(
            authorization_id=f"auth-{uuid.uuid4().hex[:12]}",
            transaction_id=contract.transaction_id,
            contract_id=contract.contract_id,
            user_id=contract.user_id,
            granted_at=now,
            expires_at=now + valid_for,
            transcript_quote=transcript_quote,
            channel=channel,
            binding_hash=contract.binding_hash(),
            max_uses=max_uses,
        )

    def invalid_reason(
        self, contract: TransactionContract, *, now: datetime | None = None
    ) -> str | None:
        """None when this authorization currently covers *contract*."""
        moment = now or utcnow()
        if self.revoked_at is not None:
            reason = self.revoked_reason or "no reason given"
            return f"authorization was revoked: {reason}"
        if moment >= self.expires_at:
            return "authorization expired"
        if self.uses >= self.max_uses:
            return "authorization already used"
        if self.contract_id != contract.contract_id:
            return "authorization is for a different contract"
        if self.binding_hash != contract.binding_hash():
            return "the contract terms changed after this authorization was granted"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "transaction_id": self.transaction_id,
            "contract_id": self.contract_id,
            "user_id": self.user_id,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "transcript_quote": self.transcript_quote,
            "channel": self.channel,
            "binding_hash": self.binding_hash,
            "max_uses": self.max_uses,
            "uses": self.uses,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoked_reason": self.revoked_reason,
        }


@dataclass(frozen=True, slots=True)
class CheckoutMandate:
    """The exact cart the user authorized, as a handed-over artifact."""

    mandate_id: str
    transaction_id: str
    contract_id: str
    checkout: ObservedCheckout
    created_at: datetime = field(default_factory=utcnow)
    sandbox: bool = False

    @classmethod
    def create(
        cls,
        contract: TransactionContract,
        checkout: ObservedCheckout,
        *,
        sandbox: bool = False,
    ) -> CheckoutMandate:
        return cls(
            mandate_id=f"checkout-{uuid.uuid4().hex[:12]}",
            transaction_id=contract.transaction_id,
            contract_id=contract.contract_id,
            checkout=checkout,
            sandbox=sandbox or contract.sandbox,
        )

    @property
    def checkout_hash(self) -> str:
        return self.checkout.checkout_hash()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "transaction_id": self.transaction_id,
            "contract_id": self.contract_id,
            "checkout": self.checkout.to_dict(),
            "checkout_hash": self.checkout_hash,
            "created_at": self.created_at.isoformat(),
            "sandbox": self.sandbox,
        }


@dataclass(frozen=True, slots=True)
class PaymentMandate:
    """Authority to pay for one specific checkout.

    The ``checkout_hash`` is the whole point: this mandate is spendable
    against that cart and nothing else.  A replay against a different cart
    fails :meth:`covers`, so a captured mandate is not a blank cheque.
    """

    mandate_id: str
    transaction_id: str
    checkout_mandate_id: str
    checkout_hash: str
    amount: Money
    payment_method_id: str
    expires_at: datetime
    created_at: datetime = field(default_factory=utcnow)
    sandbox: bool = False

    @classmethod
    def create(
        cls,
        checkout_mandate: CheckoutMandate,
        *,
        payment_method_id: str,
        valid_for: timedelta = timedelta(minutes=10),
        sandbox: bool = False,
    ) -> PaymentMandate:
        return cls(
            mandate_id=f"payment-{uuid.uuid4().hex[:12]}",
            transaction_id=checkout_mandate.transaction_id,
            checkout_mandate_id=checkout_mandate.mandate_id,
            checkout_hash=checkout_mandate.checkout_hash,
            amount=checkout_mandate.checkout.total_amount,
            payment_method_id=payment_method_id,
            expires_at=utcnow() + valid_for,
            sandbox=sandbox or checkout_mandate.sandbox,
        )

    def covers(
        self, checkout: ObservedCheckout, *, now: datetime | None = None
    ) -> str | None:
        """None when this mandate may pay for *checkout*, else the reason."""
        if (now or utcnow()) >= self.expires_at:
            return "payment mandate expired"
        if checkout.checkout_hash() != self.checkout_hash:
            return (
                "payment mandate was minted for a different checkout; it cannot "
                "be replayed against this cart"
            )
        if checkout.total_amount != self.amount:
            return (
                f"payment mandate covers {self.amount} but the cart totals "
                f"{checkout.total_amount}"
            )
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "transaction_id": self.transaction_id,
            "checkout_mandate_id": self.checkout_mandate_id,
            "checkout_hash": self.checkout_hash,
            "amount": self.amount.to_dict(),
            "payment_method_id": self.payment_method_id,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "sandbox": self.sandbox,
        }
