"""Transaction authority and types -- Phases 1-2.

The rule this module exists to enforce (§25, invariants 6-8):

    "Find me a laptop" is not "buy me a laptop."

Discovery, planning, booking, payment and sharing are five separate grants.
Holding one says nothing about holding another, so they are modelled as
distinct members of a set rather than as levels on a scale -- there is no
ordering along which a caller could accidentally round up.

``AutonomyLevel`` from ``beacon.assurance.policy`` already answers a different
question: *who has to be present* when authority is used.  This module answers
*what the authority covers*.  Both are required, and neither implies the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from beacon.assurance import AutonomyLevel, Money, utcnow

__all__ = [
    "CONSEQUENTIAL_PERMISSIONS",
    "AuthorityError",
    "ConditionalGrant",
    "PaymentMethod",
    "Permission",
    "PermissionSet",
    "TransactionType",
]


class AuthorityError(RuntimeError):
    """Raised when an action is attempted without the matching permission."""


class TransactionType(StrEnum):
    """What kind of transaction this is (§6).

    These are *values on one aggregate*, never separate applications.  Adding a
    member must never require a new transaction model.
    """

    PURCHASE = "PURCHASE"
    BOOKING = "BOOKING"
    SERVICE = "SERVICE"
    TRANSPORT = "TRANSPORT"
    PROPERTY = "PROPERTY"
    EXAM = "EXAM"
    BILL = "BILL"
    TRANSFER = "TRANSFER"
    SUBSCRIPTION = "SUBSCRIPTION"


class PaymentMethod(StrEnum):
    """How money moves.  ``CASH`` is first-class, not a degenerate case."""

    UPI = "UPI"
    CARD = "CARD"
    BANK = "BANK"
    WALLET = "WALLET"
    NCMC = "NCMC"
    CASH = "CASH"
    OTHER = "OTHER"


class Permission(StrEnum):
    """One grant of authority over one kind of action (§25)."""

    DISCOVERY = "DISCOVERY"
    """Search, read, compare.  Costs nothing and commits to nothing."""

    PLANNING = "PLANNING"
    """Assemble a proposal.  Still commits to nothing."""

    BOOKING = "BOOKING"
    """Hold or reserve something in the real world."""

    PAYMENT = "PAYMENT"
    """Move money."""

    SHARING = "SHARING"
    """Disclose something about the user beyond the vault."""


CONSEQUENTIAL_PERMISSIONS: frozenset[Permission] = frozenset(
    {Permission.BOOKING, Permission.PAYMENT, Permission.SHARING}
)
"""Permissions whose use a third party would notice.

Discovery and planning are reversible and private; these three are not.  Any
action needing one of these requires an explicit or conditional grant -- never
a default, and never an inference from intent.
"""


@dataclass(frozen=True, slots=True)
class ConditionalGrant:
    """A grant that only applies while a stated condition holds (§24).

    Models "buy if it is under Rs 45,000": real authority, but bounded, and
    bounded by a number that code checks rather than a model asserts.
    """

    permission: Permission
    max_amount: Money | None = None
    raw_utterance: str = ""
    """The user's own words granting this.  The consent record."""

    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or utcnow()) >= self.expires_at

    def covers(self, amount: Money | None, *, now: datetime | None = None) -> bool:
        """True when this grant authorizes ``amount``.

        An unstated amount is not covered by a capped grant: "buy if under
        45,000" does not authorize a purchase of unknown price.
        """
        if self.is_expired(now=now):
            return False
        if self.max_amount is None:
            return True
        if amount is None:
            return False
        if amount.currency != self.max_amount.currency:
            return False
        return amount.minor <= self.max_amount.minor

    def to_dict(self) -> dict[str, Any]:
        return {
            "permission": str(self.permission),
            "max_amount": self.max_amount.to_dict() if self.max_amount else None,
            "raw_utterance": self.raw_utterance,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass(frozen=True, slots=True)
class PermissionSet:
    """What the user has authorized on one transaction.

    Immutable: granting returns a new set, so an audit trail is the sequence of
    sets rather than a mutable field whose history is lost.
    """

    granted: frozenset[Permission] = frozenset()
    conditional: tuple[ConditionalGrant, ...] = ()
    autonomy: AutonomyLevel = AutonomyLevel.HUMAN_PRESENT

    @classmethod
    def discovery_only(cls) -> PermissionSet:
        """The default for a fresh intent.

        Searching and planning are allowed because they are private and
        reversible.  Nothing consequential is.
        """
        return cls(granted=frozenset({Permission.DISCOVERY, Permission.PLANNING}))

    def allows(
        self,
        permission: Permission,
        *,
        amount: Money | None = None,
        now: datetime | None = None,
    ) -> bool:
        """True when ``permission`` is held outright or conditionally met."""
        if permission in self.granted:
            return True
        return any(
            g.permission is permission and g.covers(amount, now=now)
            for g in self.conditional
        )

    def require(
        self,
        permission: Permission,
        *,
        amount: Money | None = None,
        now: datetime | None = None,
    ) -> None:
        """Raise ``AuthorityError`` unless ``permission`` is held.

        The message names what was missing, because a refusal the user cannot
        interpret is a bug even when the refusal is correct.
        """
        if self.allows(permission, amount=amount, now=now):
            return
        detail = f" for {amount}" if amount is not None else ""
        raise AuthorityError(
            f"{permission} permission is not granted{detail}; "
            "the user must authorize this action explicitly"
        )

    def grant(self, *permissions: Permission) -> PermissionSet:
        """Return a new set with ``permissions`` added."""
        return replace(self, granted=self.granted | frozenset(permissions))

    def grant_conditional(self, grant: ConditionalGrant) -> PermissionSet:
        """Return a new set with one conditional grant added."""
        return replace(self, conditional=(*self.conditional, grant))

    def revoke(self, *permissions: Permission) -> PermissionSet:
        """Return a new set with ``permissions`` removed, outright and conditional."""
        drop = frozenset(permissions)
        return replace(
            self,
            granted=self.granted - drop,
            conditional=tuple(g for g in self.conditional if g.permission not in drop),
        )

    def with_autonomy(self, autonomy: AutonomyLevel) -> PermissionSet:
        return replace(self, autonomy=autonomy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "granted": sorted(str(p) for p in self.granted),
            "conditional": [g.to_dict() for g in self.conditional],
            "autonomy": str(self.autonomy),
        }
