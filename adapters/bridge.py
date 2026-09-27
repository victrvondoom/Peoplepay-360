"""The one way a capability joins a transaction.

Every adapter returns a ``CapabilityResult``; this module is the only thing that
turns one into transaction state.  Keeping it in one place means a capability
cannot invent its own way in, and the three things that must always happen --
context slot, evidence node with an honest ``SourceType``, and a ledger event --
cannot be forgotten individually.

The mappings below are deliberately explicit tables rather than string
manipulation on the capability name.  A capability that is not in the table
raises instead of defaulting, because a silent default is how the wrong
``SourceType`` gets attached to a real-money decision.
"""

from __future__ import annotations

from typing import Any

from beacon.peoplepay.nodes import PeoplePayNodeKind, SourceType
from beacon.peoplepay.transaction import CONTEXT_SLOTS, Transaction

from adapters.base import CapabilityMode, CapabilityResult

__all__ = [
    "NODE_KIND_FOR_CAPABILITY",
    "SLOT_FOR_CAPABILITY",
    "SOURCE_TYPE_FOR_CAPABILITY",
    "attach_capability_result",
]


#: capability name -> the ``CONTEXT_SLOTS`` entry it fills.
SLOT_FOR_CAPABILITY: dict[str, str] = {
    "spatial": "spatial",
    "market": "market",
    "property": "property",
    "commerce": "product",
    "booking": "booking",
    "payment": "payment",
    "resolution": "fulfillment",
}

#: capability name -> the evidence node kind its findings become.
NODE_KIND_FOR_CAPABILITY: dict[str, PeoplePayNodeKind] = {
    # Rumi measures a room; that is a system-derived observation about the
    # user's own space, so it is recorded as a system observation rather than
    # as a claim about the world.
    "spatial": PeoplePayNodeKind.SYSTEM_OBSERVATION,
    "market": PeoplePayNodeKind.PRICE_OBSERVATION,
    "property": PeoplePayNodeKind.PROPERTY,
    "commerce": PeoplePayNodeKind.PRODUCT,
    "booking": PeoplePayNodeKind.BOOKING,
    "payment": PeoplePayNodeKind.PAYMENT,
    "resolution": PeoplePayNodeKind.FULFILLMENT,
}

#: capability name -> what that provider's word is worth (Sec. 10).
#:
#: ``market`` is a MARKETPLACE_LISTING, not a PRIMARY_SOURCE: InflationForge
#: reads published city price tables, which state an asking price rather than a
#: paid one.  Calling it primary would let a scraped number settle a fact it
#: cannot settle.  ``spatial`` is SYSTEM_DERIVED because Rumi computes geometry
#: from a capture rather than being told it.
SOURCE_TYPE_FOR_CAPABILITY: dict[str, SourceType] = {
    "spatial": SourceType.SYSTEM_DERIVED,
    "market": SourceType.MARKETPLACE_LISTING,
    "property": SourceType.OFFICIAL_RECORD,
    "commerce": SourceType.MARKETPLACE_LISTING,
    "booking": SourceType.PRIMARY_SOURCE,
    "payment": SourceType.PRIMARY_SOURCE,
    "resolution": SourceType.PRIMARY_SOURCE,
}


def attach_capability_result(
    tx: Transaction,
    result: CapabilityResult,
    *,
    actor: str | None = None,
) -> str | None:
    """Attach one capability's findings to ``tx``.

    Returns the evidence node id, or ``None`` when the capability had nothing to
    attach because it is not configured.

    A ``NOT_CONFIGURED`` or ``UNAVAILABLE`` result still fills its context slot:
    the spec is explicit that "we looked and could not get it" must be visible
    rather than absent (Sec. 24).  What it does *not* do is create an evidence
    node claiming a finding, because there is no finding.
    """
    name = result.capability
    if name not in SLOT_FOR_CAPABILITY:
        raise ValueError(
            f"capability {name!r} has no declared context slot; add it to "
            "SLOT_FOR_CAPABILITY rather than letting it default"
        )
    slot = SLOT_FOR_CAPABILITY[name]
    if slot not in CONTEXT_SLOTS:
        raise ValueError(
            f"slot {slot!r} for capability {name!r} is not one of the "
            f"transaction's context slots {CONTEXT_SLOTS}"
        )

    who = actor or f"adapter.{name}"
    unusable = result.mode in (
        CapabilityMode.NOT_CONFIGURED,
        CapabilityMode.UNAVAILABLE,
    )

    tx.attach_context(
        slot,
        {
            "capability": name,
            "mode": str(result.mode),
            "available": not unusable,
            "sandbox": result.is_sandbox,
            "gaps": list(result.gaps),
            "subsystem_ref": result.subsystem_ref,
            "payload": result.payload,
        },
        actor=who,
    )

    if unusable:
        # No node: there is no finding to record. The slot above already says we
        # looked, in what mode, and what we could not get.
        return None

    source_type = SOURCE_TYPE_FOR_CAPABILITY[name]
    if result.is_sandbox:
        # A sandbox run is not a marketplace listing or a primary source; say so,
        # so DECISION_CAPABLE_SOURCES cannot be satisfied by simulated data.
        source_type = SourceType.SANDBOX

    return tx.add_evidence(
        NODE_KIND_FOR_CAPABILITY[name],
        actor=who,
        source=result.subsystem_ref or name,
        source_type=source_type,
        payload=_evidence_payload(result),
        observations=result.observations,
        confidence=result.confidence,
        sandbox=result.is_sandbox,
    )


def _evidence_payload(result: CapabilityResult) -> dict[str, Any]:
    """The node payload: the finding, plus how far it may be trusted."""
    return {
        "capability": result.capability,
        "mode": str(result.mode),
        "gaps": list(result.gaps),
        "decision_grade": result.mode is CapabilityMode.LIVE,
        **result.payload,
    }
