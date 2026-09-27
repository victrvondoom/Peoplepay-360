"""Re-export of the canonical transaction aggregate.

There is exactly one ``Transaction`` and it lives in
``beacon.peoplepay.transaction``.  This module used to hold a second
implementation of the same idea; that duplicate has been removed, because two
aggregates means two lifecycles and two ids, which is the thing the spec
forbids most plainly (Sec. 5: "ONE TRANSACTION ID").

The module is kept as a re-export so ``transaction.*`` remains a coherent
package for the store, the event bus and the adapters, and so that any import
of ``transaction.aggregate`` resolves to the canonical object rather than
silently failing or -- worse -- resurrecting a competing one.

Prefer importing from ``beacon.peoplepay`` directly in new code.
"""

from __future__ import annotations

from beacon.peoplepay.authority import (
    AuthorityError,
    ConditionalGrant,
    Permission,
    PermissionSet,
    TransactionType,
)
from beacon.peoplepay.nodes import PeoplePayNodeKind, SourceType, Visibility
from beacon.peoplepay.transaction import (
    CONTEXT_SLOTS,
    Transaction,
    TransactionOwnershipError,
)

__all__ = [
    "CONTEXT_SLOTS",
    "AuthorityError",
    "ConditionalGrant",
    "PeoplePayNodeKind",
    "Permission",
    "PermissionSet",
    "SourceType",
    "Transaction",
    "TransactionOwnershipError",
    "TransactionType",
    "Visibility",
]
