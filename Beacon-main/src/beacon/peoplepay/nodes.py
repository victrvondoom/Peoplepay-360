"""Typed PeoplePay nodes -- Phase 2.

``beacon.assurance.evidence.NodeKind`` already names 25 commerce-shaped node
kinds and is relied on by 79 passing tests, so nothing here edits it.  This
module *adds* the kinds PeoplePay needs on top, in a parallel enum, and states
the source taxonomy the brief asks for in §10.

Two separations are load-bearing and are expressed in the type system rather
than in a rule a caller has to remember:

``USER_PREFERENCE`` vs ``USER_INFERENCE``
    A thing the user said, versus a thing we guessed.  They are different
    members, so promotion cannot happen by mutating a field -- it takes
    creating a new node of a different kind, with its own provenance.  See
    ``memory.py`` for the promotion path.

``SourceType``
    "Google review", "a YouTube video" and "the merchant's own page" are not
    interchangeable, so they do not collapse into one ``review`` string.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "DECISION_CAPABLE_SOURCES",
    "PERSONAL_NODE_KINDS",
    "PeoplePayNodeKind",
    "Retention",
    "SourceType",
    "Visibility",
]


class PeoplePayNodeKind(StrEnum):
    """Node kinds PeoplePay adds.  Additive: ``NodeKind`` is untouched."""

    # --- the user themself ------------------------------------------------
    USER_FACT = "USER_FACT"
    """Something true of the user that they stated or we verified."""

    USER_PREFERENCE = "USER_PREFERENCE"
    """Something the user said they want.  Only ever created explicitly."""

    USER_INFERENCE = "USER_INFERENCE"
    """Something we guessed from behaviour.  Never authority on its own."""

    TRANSACTION_INTENT = "TRANSACTION_INTENT"

    # --- the world --------------------------------------------------------
    PRODUCT = "PRODUCT"
    MERCHANT = "MERCHANT"
    PRICE_OBSERVATION = "PRICE_OBSERVATION"
    REVIEW = "REVIEW"
    VIDEO_EVIDENCE = "VIDEO_EVIDENCE"
    COMMUNITY_EVIDENCE = "COMMUNITY_EVIDENCE"
    PROPERTY = "PROPERTY"

    # --- the transaction --------------------------------------------------
    BOOKING = "BOOKING"
    PAYMENT = "PAYMENT"
    FULFILLMENT = "FULFILLMENT"
    VERIFICATION = "VERIFICATION"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    AUTHORIZATION = "AUTHORIZATION"

    # --- us ---------------------------------------------------------------
    SYSTEM_OBSERVATION = "SYSTEM_OBSERVATION"
    """Something PeoplePay noticed about its own operation."""


PERSONAL_NODE_KINDS: frozenset[PeoplePayNodeKind] = frozenset(
    {
        PeoplePayNodeKind.USER_FACT,
        PeoplePayNodeKind.USER_PREFERENCE,
        PeoplePayNodeKind.USER_INFERENCE,
    }
)
"""Kinds that describe a person.  These default to private and never leave the
vault without an explicit visibility change."""


class SourceType(StrEnum):
    """*What kind of thing* a fact came from (§10).

    ``Provenance.source`` already records *which* provider answered.  This
    records what that provider's word is worth, which is a different question
    and must not be inferred from the hostname.
    """

    PRIMARY_SOURCE = "PRIMARY_SOURCE"
    """The party who would know: the merchant, the issuer, the exam board."""

    OFFICIAL_RECORD = "OFFICIAL_RECORD"
    """A government or regulator record."""

    USER_REVIEW = "USER_REVIEW"
    """A named platform's customer review, e.g. a Google review."""

    CREATOR_CONTENT = "CREATOR_CONTENT"
    """A video or post by a creator.  May be sponsored.  Evidence, not proof."""

    COMMUNITY_DISCUSSION = "COMMUNITY_DISCUSSION"
    """A forum or public channel thread."""

    MARKETPLACE_LISTING = "MARKETPLACE_LISTING"
    """A listing, which states an asking price rather than a paid price."""

    VERIFIED_USER_EXPERIENCE = "VERIFIED_USER_EXPERIENCE"
    """A PeoplePay user's experience, tied to a transaction we can verify."""

    SELF_REPORTED = "SELF_REPORTED"
    """The user told us.  Authoritative about them, not about the world."""

    SYSTEM_DERIVED = "SYSTEM_DERIVED"
    """We computed it.  Carries the provenance of its inputs, not more."""

    SANDBOX = "SANDBOX"
    """A local simulation.  Never a real-world claim."""


DECISION_CAPABLE_SOURCES: frozenset[SourceType] = frozenset(
    {
        SourceType.PRIMARY_SOURCE,
        SourceType.OFFICIAL_RECORD,
        SourceType.SELF_REPORTED,
        SourceType.VERIFIED_USER_EXPERIENCE,
    }
)
"""Source types a deterministic decision may rest on by itself.

Creator content, community discussion and listings are deliberately absent:
they inform a person, they do not settle a fact.  ``EvidenceClass`` still
governs freshness and conflict independently of this set.
"""


class Visibility(StrEnum):
    """Who may see an item.  Default is always the most private (§16)."""

    PRIVATE = "PRIVATE"
    SHARED_WITH_TRANSACTION = "SHARED_WITH_TRANSACTION"
    SHARED_WITH_COMMUNITY = "SHARED_WITH_COMMUNITY"
    PUBLIC = "PUBLIC"


class Retention(StrEnum):
    """How long an item may be kept (§15).  Nothing is permanent by default."""

    SESSION_ONLY = "SESSION_ONLY"
    TRANSACTION_ONLY = "TRANSACTION_ONLY"
    CASE = "CASE"
    LONG_TERM = "LONG_TERM"
