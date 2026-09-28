"""Cryptographically bind user authority to an exact checkout.

A payment permission is necessary, but it is deliberately not sufficient.  A
``MandateCapsule`` also binds the permission to the transaction, user, cart,
merchants, ceiling and expiry.  Any material checkout change therefore needs a
new capsule instead of inheriting stale consent.

The capsule contains no payment credential.  A production payment connector
must exchange it for a provider token outside model context.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from beacon.assurance import EventKind, Money, NodeKind, content_hash, utcnow
from beacon.peoplepay.authority import Permission

if TYPE_CHECKING:
    from collections.abc import Iterable

    from beacon.peoplepay.transaction import Transaction

__all__ = [
    "CartLine",
    "CheckoutSnapshot",
    "MandateCapsule",
    "MandateError",
    "MandateIssuer",
    "MandateReplay",
    "SubstitutionPolicy",
]


class MandateError(ValueError):
    """The mandate is invalid for the presented checkout."""


class MandateReplay(MandateError):
    """A single-use mandate was presented after it had been consumed."""


class SubstitutionPolicy(StrEnum):
    """How cart alternatives are authorized.

    Alternatives are represented by explicit approved cart hashes.  The label
    explains why there can be more than one; it never lets a connector invent a
    semantically "similar" product.
    """

    NONE = "NONE"
    EXPLICIT_ALTERNATIVES = "EXPLICIT_ALTERNATIVES"


@dataclass(frozen=True, slots=True)
class CartLine:
    """One exact product variant in a checkout."""

    line_id: str
    merchant_id: str
    product_id: str
    variant_id: str
    quantity: int
    unit_price: Money

    def __post_init__(self) -> None:
        for name in ("line_id", "merchant_id", "product_id", "variant_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if not isinstance(self.quantity, int) or isinstance(self.quantity, bool):
            raise TypeError("quantity must be an int")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.unit_price.minor < 0:
            raise ValueError("unit_price cannot be negative")

    @property
    def total(self) -> Money:
        return self.unit_price * self.quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "merchant_id": self.merchant_id,
            "product_id": self.product_id,
            "variant_id": self.variant_id,
            "quantity": self.quantity,
            "unit_price": self.unit_price.to_dict(),
            "line_total": self.total.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CheckoutSnapshot:
    """The complete, exact checkout state shown to the user."""

    lines: tuple[CartLine, ...]
    shipping: Money
    tax: Money
    discount: Money
    cart_hash: str = field(init=False)
    total: Money = field(init=False)
    merchant_ids: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("a checkout needs at least one line")
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("checkout line_id values must be unique")

        currency = self.lines[0].unit_price.currency
        extras = (self.shipping, self.tax, self.discount)
        if any(m.currency != currency for m in extras):
            raise ValueError("all checkout amounts must use one currency")
        if any(line.unit_price.currency != currency for line in self.lines):
            raise ValueError("all checkout lines must use one currency")
        if any(m.minor < 0 for m in extras):
            raise ValueError("shipping, tax and discount cannot be negative")

        subtotal = Money.zero(currency)
        for line in self.lines:
            subtotal += line.total
        total = subtotal + self.shipping + self.tax - self.discount
        if total.minor < 0:
            raise ValueError("discount cannot make the checkout total negative")

        canonical_lines = tuple(
            sorted(
                (line.to_dict() for line in self.lines),
                key=lambda row: row["line_id"],
            )
        )
        body = {
            "lines": canonical_lines,
            "shipping": self.shipping.to_dict(),
            "tax": self.tax.to_dict(),
            "discount": self.discount.to_dict(),
            "total": total.to_dict(),
        }
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "cart_hash", content_hash(body))
        object.__setattr__(
            self,
            "merchant_ids",
            tuple(sorted({line.merchant_id for line in self.lines})),
        )

    @classmethod
    def create(
        cls,
        lines: Iterable[CartLine],
        *,
        shipping: Money | None = None,
        tax: Money | None = None,
        discount: Money | None = None,
    ) -> CheckoutSnapshot:
        frozen = tuple(lines)
        if not frozen:
            raise ValueError("a checkout needs at least one line")
        currency = frozen[0].unit_price.currency
        return cls(
            lines=frozen,
            shipping=shipping or Money.zero(currency),
            tax=tax or Money.zero(currency),
            discount=discount or Money.zero(currency),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [line.to_dict() for line in self.lines],
            "shipping": self.shipping.to_dict(),
            "tax": self.tax.to_dict(),
            "discount": self.discount.to_dict(),
            "total": self.total.to_dict(),
            "cart_hash": self.cart_hash,
            "merchant_ids": list(self.merchant_ids),
        }


@dataclass(frozen=True, slots=True)
class MandateCapsule:
    """A signed, short-lived and single-use authorization envelope."""

    mandate_id: str
    transaction_id: str
    user_id: str
    instruction_hash: str
    approved_cart_hashes: tuple[str, ...]
    merchant_ids: tuple[str, ...]
    max_total: Money
    substitution_policy: SubstitutionPolicy
    issued_at: datetime
    expires_at: datetime
    nonce: str
    key_id: str
    signature: str

    def __post_init__(self) -> None:
        required = (
            self.mandate_id,
            self.transaction_id,
            self.user_id,
            self.instruction_hash,
            self.nonce,
            self.key_id,
        )
        if any(not item.strip() for item in required):
            raise ValueError("mandate identity and binding fields are required")
        if not self.approved_cart_hashes or not self.merchant_ids:
            raise ValueError("mandate must approve a cart and at least one merchant")
        if self.max_total.minor < 0:
            raise ValueError("mandate ceiling cannot be negative")
        if self.expires_at <= self.issued_at:
            raise ValueError("mandate must expire after it is issued")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
            "instruction_hash": self.instruction_hash,
            "approved_cart_hashes": list(self.approved_cart_hashes),
            "merchant_ids": list(self.merchant_ids),
            "max_total": self.max_total.to_dict(),
            "substitution_policy": str(self.substitution_policy),
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "nonce": self.nonce,
            "key_id": self.key_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "signature": self.signature}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MandateCapsule:
        return cls(
            mandate_id=str(raw["mandate_id"]),
            transaction_id=str(raw["transaction_id"]),
            user_id=str(raw["user_id"]),
            instruction_hash=str(raw["instruction_hash"]),
            approved_cart_hashes=tuple(raw["approved_cart_hashes"]),
            merchant_ids=tuple(raw["merchant_ids"]),
            max_total=Money.from_dict(raw["max_total"]),
            substitution_policy=SubstitutionPolicy(raw["substitution_policy"]),
            issued_at=datetime.fromisoformat(raw["issued_at"]),
            expires_at=datetime.fromisoformat(raw["expires_at"]),
            nonce=str(raw["nonce"]),
            key_id=str(raw["key_id"]),
            signature=str(raw["signature"]),
        )


class MandateIssuer:
    """Issue, verify and consume capsules with one active signing key.

    The in-memory consumed set is suitable for tests and a sandbox.  Production
    must put the same atomic claim behind a durable store before enabling a live
    connector; the build sequence makes that a payment release gate.
    """

    MAX_VALIDITY = timedelta(hours=1)

    def __init__(self, signing_key: bytes, *, key_id: str = "local-v1") -> None:
        if len(signing_key) < 32:
            raise ValueError("mandate signing_key must contain at least 32 bytes")
        if not key_id.strip():
            raise ValueError("key_id is required")
        self._key = signing_key
        self.key_id = key_id
        self._consumed: set[str] = set()

    def _sign(self, body: dict[str, Any]) -> str:
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hmac.new(self._key, canonical.encode(), hashlib.sha256).hexdigest()

    def issue(
        self,
        transaction: Transaction,
        checkout: CheckoutSnapshot,
        *,
        actor: str,
        expires_in: timedelta = timedelta(minutes=10),
        approved_alternatives: Iterable[CheckoutSnapshot] = (),
    ) -> MandateCapsule:
        if expires_in <= timedelta(0) or expires_in > self.MAX_VALIDITY:
            raise ValueError("mandate validity must be positive and at most one hour")
        if transaction.has_sandbox_evidence:
            raise MandateError("sandbox evidence cannot authorize a real payment")

        transaction.require_permission(
            Permission.PAYMENT, amount=checkout.total, actor=actor
        )
        alternatives = tuple(approved_alternatives)
        for alternative in alternatives:
            if alternative.total > checkout.total:
                raise MandateError(
                    "an alternative above the approved ceiling needs fresh consent"
                )
            if alternative.merchant_ids != checkout.merchant_ids:
                raise MandateError(
                    "an alternative with different merchants needs fresh consent"
                )

        now = utcnow()
        hashes = (checkout.cart_hash, *(item.cart_hash for item in alternatives))
        draft = MandateCapsule(
            mandate_id=f"mandate-{uuid.uuid4().hex[:16]}",
            transaction_id=transaction.transaction_id,
            user_id=transaction.user_id,
            instruction_hash=content_hash(transaction.raw_utterance),
            approved_cart_hashes=hashes,
            merchant_ids=checkout.merchant_ids,
            max_total=checkout.total,
            substitution_policy=(
                SubstitutionPolicy.EXPLICIT_ALTERNATIVES
                if alternatives
                else SubstitutionPolicy.NONE
            ),
            issued_at=now,
            expires_at=now + expires_in,
            nonce=secrets.token_hex(16),
            key_id=self.key_id,
            signature="",
        )
        capsule = MandateCapsule(
            **{
                **draft.unsigned_dict(),
                "max_total": draft.max_total,
                "substitution_policy": draft.substitution_policy,
                "issued_at": draft.issued_at,
                "expires_at": draft.expires_at,
                "approved_cart_hashes": draft.approved_cart_hashes,
                "merchant_ids": draft.merchant_ids,
                "signature": self._sign(draft.unsigned_dict()),
            }
        )

        node = transaction.graph.add(
            NodeKind.PAYMENT_MANDATE,
            actor=actor,
            payload={
                "mandate_id": capsule.mandate_id,
                "cart_hashes": list(capsule.approved_cart_hashes),
                "merchant_ids": list(capsule.merchant_ids),
                "max_total": capsule.max_total.to_dict(),
                "expires_at": capsule.expires_at.isoformat(),
                "key_id": capsule.key_id,
            },
        )
        transaction.ledger.append(
            EventKind.PAYMENT_MANDATE_CREATED,
            actor=actor,
            detail={
                "mandate_id": capsule.mandate_id,
                "evidence_node_id": node.node_id,
                "cart_hash": checkout.cart_hash,
                "max_total": checkout.total.to_dict(),
                "expires_at": capsule.expires_at.isoformat(),
            },
        )
        return capsule

    def verify(
        self,
        capsule: MandateCapsule,
        checkout: CheckoutSnapshot,
        *,
        transaction_id: str,
        user_id: str,
        now: datetime | None = None,
    ) -> None:
        if capsule.key_id != self.key_id:
            raise MandateError("mandate was signed by an unknown key")
        expected = self._sign(capsule.unsigned_dict())
        if not hmac.compare_digest(capsule.signature, expected):
            raise MandateError("mandate signature is invalid")
        if capsule.mandate_id in self._consumed:
            raise MandateReplay("mandate has already been consumed")
        if capsule.transaction_id != transaction_id or capsule.user_id != user_id:
            raise MandateError("mandate is bound to a different transaction or user")
        if (now or utcnow()) >= capsule.expires_at:
            raise MandateError("mandate has expired")
        if checkout.cart_hash not in capsule.approved_cart_hashes:
            raise MandateError("checkout cart was not approved")
        if checkout.merchant_ids != capsule.merchant_ids:
            raise MandateError("checkout merchants changed after approval")
        if checkout.total.currency != capsule.max_total.currency:
            raise MandateError("checkout currency changed after approval")
        if checkout.total > capsule.max_total:
            raise MandateError("checkout total exceeds the approved ceiling")

    def consume(
        self,
        capsule: MandateCapsule,
        checkout: CheckoutSnapshot,
        *,
        transaction_id: str,
        user_id: str,
        now: datetime | None = None,
    ) -> None:
        self.verify(
            capsule,
            checkout,
            transaction_id=transaction_id,
            user_id=user_id,
            now=now,
        )
        self._consumed.add(capsule.mandate_id)
