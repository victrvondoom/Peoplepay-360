"""The personal memory vault -- Phase 3.

PROXY (``CONSUMER-main/backend/app/services/memory_service.py``) already
established the layering this needs, and §13 says to reuse it rather than invent
a fourth memory system.  Its shape is:

    ``get_conversation_memory(case_id)``   this exchange
    ``get_case_memory(case_id, user_id)``  this case and its artefacts
    ``get_user_memory(user_id)``           across cases, capped
    ``format_memory_for_prompt(...)``      render for a model to read

The same reads appear here, with ``case`` generalised to ``transaction`` because
in PeoplePay the transaction is the unit of work.  PROXY's own module keeps its
names and is not modified; this is the PeoplePay-side vault.  When the two are
wired together, PROXY's async repository becomes one backing store behind this
interface -- which is why the method names deliberately match.

Two things PROXY's version does not have, and §14-16 require:

*Retention and visibility on every item.*  Nothing is permanent by default and
nothing is shared by default.

*A hard wall between preference and inference.*  ``promote_inference`` creates a
**new** ``USER_PREFERENCE`` item and leaves the inference untouched, so the
audit trail shows both the guess and the confirmation.  There is no code path
that mutates an inference into a preference, which is invariant 3.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from beacon.assurance import utcnow
from beacon.peoplepay.nodes import (
    PERSONAL_NODE_KINDS,
    PeoplePayNodeKind,
    Retention,
    SourceType,
    Visibility,
)

__all__ = [
    "MemoryItem",
    "MemoryScope",
    "MemoryVault",
    "PromotionError",
    "VisibilityError",
]


class PromotionError(RuntimeError):
    """Raised when an inference is promoted without explicit confirmation."""


class VisibilityError(RuntimeError):
    """Raised when private memory would be exposed without permission."""


class MemoryScope:
    """The layer a memory item belongs to.

    Plain string constants rather than an enum, to match the vocabulary PROXY
    already uses in its repository rows.
    """

    CONVERSATION = "conversation"
    TRANSACTION = "transaction"
    CASE = "case"
    LONG_TERM = "long_term"

    ALL: tuple[str, ...] = (CONVERSATION, TRANSACTION, CASE, LONG_TERM)


@dataclass(frozen=True, slots=True)
class MemoryItem:
    """One remembered thing, with everything needed to judge and expire it (§14)."""

    item_id: str
    user_id: str
    kind: PeoplePayNodeKind
    key: str
    value: Any
    source: SourceType
    scope: str = MemoryScope.TRANSACTION
    confidence: float | None = None
    """``None`` for an explicit user statement -- it is not a probability."""

    created_at: datetime = field(default_factory=utcnow)
    last_confirmed: datetime | None = None
    visibility: Visibility = Visibility.PRIVATE
    retention: Retention = Retention.TRANSACTION_ONLY
    transaction_id: str | None = None
    derived_from: str | None = None
    """The item this one was promoted from, if any.  Keeps the chain visible."""

    note: str = ""

    def __post_init__(self) -> None:
        if (
            self.kind is PeoplePayNodeKind.USER_PREFERENCE
            and self.confidence is not None
        ):
            # A stated preference is not a guess with a high score.
            raise ValueError(
                "USER_PREFERENCE must not carry a confidence score; it is an "
                "explicit statement, not an estimate"
            )
        if self.kind is PeoplePayNodeKind.USER_INFERENCE and self.confidence is None:
            raise ValueError(
                "USER_INFERENCE must carry a confidence score; an unquantified "
                "guess cannot be told apart from a fact"
            )
        if (
            self.visibility is not Visibility.PRIVATE
            and self.kind in PERSONAL_NODE_KINDS
            and not self.note
        ):
            raise ValueError(
                "a non-private personal memory item must record why it was "
                "shared; set note to the consent reference"
            )

    @property
    def is_explicit(self) -> bool:
        """True when the user said this themselves."""
        return self.source is SourceType.SELF_REPORTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "user_id": self.user_id,
            "kind": str(self.kind),
            "key": self.key,
            "value": self.value,
            "source": str(self.source),
            "scope": self.scope,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "last_confirmed": (
                self.last_confirmed.isoformat() if self.last_confirmed else None
            ),
            "visibility": str(self.visibility),
            "retention": str(self.retention),
            "transaction_id": self.transaction_id,
            "derived_from": self.derived_from,
            "note": self.note,
        }


class MemoryVault:
    """One user's private memory, across the four scopes.

    In-memory for Phase 3.  The interface is the deliverable: it mirrors PROXY's
    reads so that swapping this for PROXY's repository is a constructor change
    rather than a rewrite of every caller.
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._items: list[MemoryItem] = []

    def __len__(self) -> int:
        return len(self._items)

    # --- writing ----------------------------------------------------------

    def remember(
        self,
        *,
        kind: PeoplePayNodeKind,
        key: str,
        value: Any,
        source: SourceType,
        scope: str = MemoryScope.TRANSACTION,
        confidence: float | None = None,
        retention: Retention = Retention.TRANSACTION_ONLY,
        transaction_id: str | None = None,
        note: str = "",
    ) -> MemoryItem:
        """Store one item.  Always private; visibility is changed only by ``share``."""
        if scope not in MemoryScope.ALL:
            raise ValueError(
                f"unknown memory scope {scope!r}; known: {MemoryScope.ALL}"
            )
        item = MemoryItem(
            item_id=f"mem-{uuid.uuid4().hex[:12]}",
            user_id=self.user_id,
            kind=kind,
            key=key,
            value=value,
            source=source,
            scope=scope,
            confidence=confidence,
            retention=retention,
            transaction_id=transaction_id,
            note=note,
        )
        self._items.append(item)
        return item

    def state_preference(
        self,
        *,
        key: str,
        value: Any,
        retention: Retention = Retention.LONG_TERM,
        transaction_id: str | None = None,
        note: str = "",
    ) -> MemoryItem:
        """Record a preference the user stated themselves (§8)."""
        return self.remember(
            kind=PeoplePayNodeKind.USER_PREFERENCE,
            key=key,
            value=value,
            source=SourceType.SELF_REPORTED,
            scope=MemoryScope.LONG_TERM,
            retention=retention,
            transaction_id=transaction_id,
            note=note,
        )

    def infer(
        self,
        *,
        key: str,
        value: Any,
        confidence: float,
        transaction_id: str | None = None,
        note: str = "",
    ) -> MemoryItem:
        """Record an inference from behaviour.  Never authority on its own."""
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return self.remember(
            kind=PeoplePayNodeKind.USER_INFERENCE,
            key=key,
            value=value,
            source=SourceType.SYSTEM_DERIVED,
            scope=MemoryScope.LONG_TERM,
            confidence=confidence,
            retention=Retention.LONG_TERM,
            transaction_id=transaction_id,
            note=note,
        )

    def promote_inference(
        self,
        item_id: str,
        *,
        confirmed_by_user: bool,
        raw_utterance: str = "",
    ) -> MemoryItem:
        """Turn an inference into a preference -- only on explicit confirmation.

        The inference is **not** modified.  A new ``USER_PREFERENCE`` item is
        created, pointing back at it via ``derived_from``, so the record shows
        that we guessed and then asked.  This is invariant 3, and the reason it
        is a separate method rather than a settable field.
        """
        if not confirmed_by_user:
            raise PromotionError(
                "an inference cannot become a preference without the user's "
                "explicit confirmation"
            )
        source = self.get(item_id)
        if source.kind is not PeoplePayNodeKind.USER_INFERENCE:
            raise PromotionError(
                f"only a USER_INFERENCE can be promoted; {item_id} is {source.kind}"
            )
        promoted = MemoryItem(
            item_id=f"mem-{uuid.uuid4().hex[:12]}",
            user_id=self.user_id,
            kind=PeoplePayNodeKind.USER_PREFERENCE,
            key=source.key,
            value=source.value,
            source=SourceType.SELF_REPORTED,
            scope=MemoryScope.LONG_TERM,
            confidence=None,
            last_confirmed=utcnow(),
            retention=Retention.LONG_TERM,
            transaction_id=source.transaction_id,
            derived_from=source.item_id,
            note=raw_utterance or "confirmed by user",
        )
        self._items.append(promoted)
        return promoted

    def share(
        self,
        item_id: str,
        *,
        visibility: Visibility,
        consent_reference: str,
    ) -> MemoryItem:
        """Widen one item's visibility, with a consent reference (§16, invariant 5).

        Replaces the item in place in the list, keeping ``item_id`` stable so
        references elsewhere stay valid, and requires a consent reference so a
        later audit can find *why* it was shared.
        """
        if not consent_reference.strip():
            raise VisibilityError(
                "sharing personal memory requires a consent reference recording "
                "what the user agreed to"
            )
        item = self.get(item_id)
        shared = replace(item, visibility=visibility, note=consent_reference)
        self._items = [shared if i.item_id == item_id else i for i in self._items]
        return shared

    def forget_scope(self, scope: str) -> int:
        """Drop everything in one scope.  Returns how many items went."""
        before = len(self._items)
        self._items = [i for i in self._items if i.scope != scope]
        return before - len(self._items)

    def expire(self, retention: Retention) -> int:
        """Drop everything with a given retention class (§15)."""
        before = len(self._items)
        self._items = [i for i in self._items if i.retention is not retention]
        return before - len(self._items)

    # --- reading, mirroring PROXY's interface ------------------------------

    def get(self, item_id: str) -> MemoryItem:
        for item in self._items:
            if item.item_id == item_id:
                return item
        raise KeyError(f"no memory item {item_id!r}")

    def get_conversation_memory(self, transaction_id: str) -> list[MemoryItem]:
        """This exchange only -- the session-scoped layer."""
        return [
            i
            for i in self._items
            if i.scope == MemoryScope.CONVERSATION
            and i.transaction_id == transaction_id
        ]

    def get_transaction_memory(self, transaction_id: str) -> list[MemoryItem]:
        """Everything remembered about one transaction."""
        return [i for i in self._items if i.transaction_id == transaction_id]

    def get_user_memory(
        self,
        *,
        kinds: tuple[PeoplePayNodeKind, ...] | None = None,
        include_inferences: bool = False,
    ) -> list[MemoryItem]:
        """Long-term cross-transaction memory.

        Inferences are excluded unless asked for, so a caller that wants "what
        the user told us" cannot accidentally receive "what we guessed".
        """
        items = [i for i in self._items if i.scope == MemoryScope.LONG_TERM]
        if not include_inferences:
            items = [i for i in items if i.kind is not PeoplePayNodeKind.USER_INFERENCE]
        if kinds is not None:
            items = [i for i in items if i.kind in kinds]
        return items

    def preferences(self) -> list[MemoryItem]:
        return [i for i in self._items if i.kind is PeoplePayNodeKind.USER_PREFERENCE]

    def inferences(self) -> list[MemoryItem]:
        return [i for i in self._items if i.kind is PeoplePayNodeKind.USER_INFERENCE]

    def shareable(self, visibility: Visibility) -> list[MemoryItem]:
        """Items the user has actually allowed at ``visibility`` or wider."""
        order = {
            Visibility.PRIVATE: 0,
            Visibility.SHARED_WITH_TRANSACTION: 1,
            Visibility.SHARED_WITH_COMMUNITY: 2,
            Visibility.PUBLIC: 3,
        }
        want = order[visibility]
        if want == 0:
            return []
        return [i for i in self._items if order[i.visibility] >= want]

    def format_for_prompt(self, *, transaction_id: str | None = None) -> str:
        """Render memory as text a model may read (mirrors PROXY's helper).

        Only preferences and facts are rendered.  Inferences are withheld: a
        model that reads its own earlier guess as context will restate it with
        more confidence than it earned.
        """
        lines: list[str] = []
        prefs = self.preferences()
        if prefs:
            lines.append("Stated preferences:")
            lines.extend(f"- {p.key}: {p.value}" for p in prefs)
        facts = [i for i in self._items if i.kind is PeoplePayNodeKind.USER_FACT]
        if facts:
            lines.append("Known facts:")
            lines.extend(f"- {f.key}: {f.value}" for f in facts)
        if transaction_id:
            local = self.get_transaction_memory(transaction_id)
            if local:
                lines.append(f"This transaction has {len(local)} remembered item(s).")
        pending = self.inferences()
        if pending:
            lines.append(
                f"({len(pending)} unconfirmed inference(s) withheld; "
                "ask before relying on them.)"
            )
        return "\n".join(lines)
