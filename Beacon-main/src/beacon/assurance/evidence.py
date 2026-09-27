"""Evidence, provenance and the evidence graph.

Two rules are load-bearing here, and both are enforced by types rather than
by asking a model nicely:

1. **Nothing is asserted without a source.**  An :class:`Observation` cannot
   be constructed without a :class:`Provenance`, and a missing fact is a
   real value (:class:`EvidenceClass`) rather than a plausible guess.
2. **Sandbox never passes as real.**  An observation carries its own
   ``evidence_class``; :attr:`Observation.is_decision_grade` is what the
   policy engine consults, and ``SANDBOX`` is not decision grade unless the
   caller explicitly opts in.

The graph is append-only.  Nodes are immutable, edges are typed, and
:meth:`EvidenceGraph.reconstruct` walks the whole thing so a dispute package
can be rebuilt months later from the same rows.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

__all__ = [
    "EdgeKind",
    "EvidenceClass",
    "EvidenceEdge",
    "EvidenceGraph",
    "EvidenceNode",
    "NodeKind",
    "Observation",
    "Provenance",
    "conflicting",
    "content_hash",
    "unavailable",
    "utcnow",
]


def utcnow() -> datetime:
    """Single clock for the assurance layer, always tz-aware UTC."""
    return datetime.now(tz=UTC)


def content_hash(value: Any) -> str:
    """Stable sha256 over a JSON-like value, for tamper-evidence.

    Sorted keys so the same content always hashes the same, and ``default=str``
    so datetimes and Decimals hash by their string form rather than raising.
    """
    canonical = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class EvidenceClass(StrEnum):
    """How much weight a fact may carry.

    ``UNKNOWN`` and ``UNAVAILABLE`` are first-class answers: the spec forbids
    inventing a value to fill a gap, so the gap gets a name instead.
    """

    VERIFIED = "VERIFIED"
    """Observed from a source we authenticated, fresh enough to act on."""

    UNVERIFIED = "UNVERIFIED"
    """Observed, but the source could not be authenticated."""

    STALE = "STALE"
    """Observed, source fine, but older than the caller's freshness window."""

    CONFLICTING = "CONFLICTING"
    """Two or more sources disagree; a human or a tiebreak policy must decide."""

    UNAVAILABLE = "UNAVAILABLE"
    """We looked and could not obtain it.  Never to be replaced by a guess."""

    UNKNOWN = "UNKNOWN"
    """We have not looked yet."""

    SANDBOX = "SANDBOX"
    """Produced by a local sandbox adapter.  Never a real-world claim."""


_DECISION_GRADE: frozenset[EvidenceClass] = frozenset(
    {EvidenceClass.VERIFIED, EvidenceClass.UNVERIFIED}
)

# Worst-to-best, for ``EvidenceNode.weakest_class``.
_CLASS_ORDER: tuple[EvidenceClass, ...] = (
    EvidenceClass.UNAVAILABLE,
    EvidenceClass.UNKNOWN,
    EvidenceClass.CONFLICTING,
    EvidenceClass.SANDBOX,
    EvidenceClass.STALE,
    EvidenceClass.UNVERIFIED,
    EvidenceClass.VERIFIED,
)


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a fact came from, precisely enough to re-check it later."""

    source: str
    """Stable identifier of the provider, e.g. ``"sandbox.catalog"``."""

    retrieved_at: datetime
    source_url: str | None = None
    raw_reference: str | None = None
    """Pointer to the stored raw response (S3 key, row id) if one was kept."""

    raw_hash: str | None = None
    """Hash of the raw response, so a later dispute can prove it is unaltered."""

    adapter: str | None = None
    sandbox: bool = False
    """True when produced by a sandbox adapter.  Propagates into the node."""

    def age(self, *, now: datetime | None = None) -> timedelta:
        return (now or utcnow()) - self.retrieved_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "retrieved_at": self.retrieved_at.isoformat(),
            "source_url": self.source_url,
            "raw_reference": self.raw_reference,
            "raw_hash": self.raw_hash,
            "adapter": self.adapter,
            "sandbox": self.sandbox,
        }


@dataclass(frozen=True, slots=True)
class Observation:
    """One external fact, its value, and how much we trust it.

    ``value`` is ``None`` whenever the class is ``UNAVAILABLE``/``UNKNOWN`` --
    an unavailable price has no number attached, by construction.
    """

    field: str
    value: Any
    provenance: Provenance
    evidence_class: EvidenceClass = EvidenceClass.UNVERIFIED
    normalized_value: Any = None
    note: str = ""

    def __post_init__(self) -> None:
        # A sandbox provenance can never launder itself into a real class.
        if self.provenance.sandbox and self.evidence_class in _DECISION_GRADE:
            object.__setattr__(self, "evidence_class", EvidenceClass.SANDBOX)
        # No value may ride along with a non-answer.
        if (
            self.evidence_class in (EvidenceClass.UNAVAILABLE, EvidenceClass.UNKNOWN)
            and self.value is not None
        ):
            raise ValueError(
                f"observation of {self.field!r} is {self.evidence_class} "
                "but carries a value; a missing fact must not be filled in"
            )

    @property
    def is_decision_grade(self) -> bool:
        """True when a deterministic policy may act on this value.

        Sandbox observations are deliberately excluded: the sandbox demo path
        must opt in explicitly rather than inherit trust.
        """
        return self.evidence_class in _DECISION_GRADE

    def aged(self, max_age: timedelta, *, now: datetime | None = None) -> Observation:
        """Return self, or a ``STALE`` copy when past *max_age*."""
        if not self.is_decision_grade:
            return self
        if self.provenance.age(now=now) > max_age:
            return replace(self, evidence_class=EvidenceClass.STALE)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "normalized_value": self.normalized_value,
            "evidence_class": str(self.evidence_class),
            "note": self.note,
            "provenance": self.provenance.to_dict(),
        }


def unavailable(
    field_name: str, source: str, *, note: str = "", sandbox: bool = False
) -> Observation:
    """The honest answer when a lookup returns nothing."""
    return Observation(
        field=field_name,
        value=None,
        provenance=Provenance(source=source, retrieved_at=utcnow(), sandbox=sandbox),
        evidence_class=EvidenceClass.UNAVAILABLE,
        note=note,
    )


def conflicting(field_name: str, candidates: list[Observation]) -> Observation:
    """Fold disagreeing observations into one explicit conflict.

    The candidate values are kept in ``note`` so a reviewer can see the
    disagreement, but no winner is picked here -- that is a policy decision.
    """
    if not candidates:
        raise ValueError("conflicting() needs at least one candidate")
    shown = ", ".join(f"{o.provenance.source}={o.value!r}" for o in candidates)
    return Observation(
        field=field_name,
        value=None,
        provenance=candidates[0].provenance,
        evidence_class=EvidenceClass.CONFLICTING,
        note=f"sources disagree: {shown}",
    )


class NodeKind(StrEnum):
    """The node types that make up a transaction's evidence graph."""

    INTENT = "INTENT"
    USER_POLICY = "USER_POLICY"

    # --- real-world context contributed by the capability subsystems -----
    # Added for the integrated system: spatial (Rumi), property (InHeir),
    # document and scan evidence.  Additive only -- no existing member moved.
    SPATIAL_CONTEXT = "SPATIAL_CONTEXT"
    """A room capture: dimensions, walls, openings, clearances, free floor."""

    SPATIAL_CONSTRAINT = "SPATIAL_CONSTRAINT"
    """A derived limit a candidate must satisfy, e.g. max desk width."""

    PLACEMENT_CHECK = "PLACEMENT_CHECK"
    """Deterministic verdict that a product fits a specific spot."""

    PROPERTY = "PROPERTY"
    PROPERTY_EVIDENCE = "PROPERTY_EVIDENCE"
    LOCATION_EVIDENCE = "LOCATION_EVIDENCE"
    DOCUMENT = "DOCUMENT"
    DOCUMENT_EVIDENCE = "DOCUMENT_EVIDENCE"
    SCAN = "SCAN"
    """A camera frame and what the router classified it as."""

    MARKET_EVIDENCE = "MARKET_EVIDENCE"
    """Historical / comparative price context, distinct from a live quote."""

    BASKET = "BASKET"
    """A multi-item plan evaluated as one budget."""

    BOOKING = "BOOKING"
    RESOLUTION = "RESOLUTION"
    """Outcome of a dispute / refund workflow."""

    PRODUCT = "PRODUCT"
    OFFER = "OFFER"
    MERCHANT = "MERCHANT"
    PRICE_EVIDENCE = "PRICE_EVIDENCE"
    MERCHANT_EVIDENCE = "MERCHANT_EVIDENCE"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    CONTRACT = "CONTRACT"
    CHECKOUT_MANDATE = "CHECKOUT_MANDATE"
    PAYMENT_MANDATE = "PAYMENT_MANDATE"
    AUTHORIZATION = "AUTHORIZATION"
    PAYMENT = "PAYMENT"
    CHECKOUT_RECEIPT = "CHECKOUT_RECEIPT"
    PAYMENT_RECEIPT = "PAYMENT_RECEIPT"
    ORDER = "ORDER"
    SHIPMENT = "SHIPMENT"
    DELIVERY = "DELIVERY"
    VERIFICATION = "VERIFICATION"
    RECONCILIATION = "RECONCILIATION"
    SETTLEMENT = "SETTLEMENT"
    REFUND = "REFUND"
    DISPUTE = "DISPUTE"
    EXCEPTION = "EXCEPTION"
    AGENT_ACTION = "AGENT_ACTION"


class EdgeKind(StrEnum):
    """Typed relationships, so the graph is walkable rather than a soup."""

    DERIVED_FROM = "DERIVED_FROM"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    AUTHORIZES = "AUTHORIZES"
    BINDS = "BINDS"
    FULFILS = "FULFILS"
    VERIFIES = "VERIFIES"
    DISPUTES = "DISPUTES"
    SUPERSEDES = "SUPERSEDES"
    CONSTRAINS = "CONSTRAINS"
    """Source imposes a limit the destination must satisfy (spatial, budget)."""

    SATISFIES = "SATISFIES"
    """Destination was checked against a constraint and passed."""

    CLASSIFIED_AS = "CLASSIFIED_AS"
    """A scan was routed to a capability as this kind of thing."""

    RESOLVES = "RESOLVES"
    """Destination closes out the exception the source raised."""


@dataclass(frozen=True, slots=True)
class EvidenceNode:
    """An immutable node.  ``node_hash`` covers the payload and observations."""

    node_id: str
    transaction_id: str
    kind: NodeKind
    actor: str
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    observations: tuple[Observation, ...] = ()
    confidence: float | None = None
    node_hash: str = ""

    @property
    def is_sandbox(self) -> bool:
        return any(o.provenance.sandbox for o in self.observations)

    @property
    def weakest_class(self) -> EvidenceClass:
        """The least trustworthy class among this node's observations."""
        if not self.observations:
            return EvidenceClass.UNKNOWN
        return min(
            (o.evidence_class for o in self.observations),
            key=_CLASS_ORDER.index,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "transaction_id": self.transaction_id,
            "kind": str(self.kind),
            "actor": self.actor,
            "created_at": self.created_at.isoformat(),
            "payload": self.payload,
            "observations": [o.to_dict() for o in self.observations],
            "confidence": self.confidence,
            "node_hash": self.node_hash,
            "sandbox": self.is_sandbox,
            "weakest_class": str(self.weakest_class),
        }


@dataclass(frozen=True, slots=True)
class EvidenceEdge:
    edge_id: str
    transaction_id: str
    src: str
    dst: str
    kind: EdgeKind
    created_at: datetime
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "transaction_id": self.transaction_id,
            "src": self.src,
            "dst": self.dst,
            "kind": str(self.kind),
            "created_at": self.created_at.isoformat(),
            "note": self.note,
        }


class EvidenceGraph:
    """Append-only evidence graph for exactly one transaction.

    There is no ``remove`` and no ``update``: a superseded claim is a new node
    joined by a ``SUPERSEDES`` edge, so the history of what we believed and
    when stays intact for a dispute.
    """

    def __init__(self, transaction_id: str) -> None:
        self.transaction_id = transaction_id
        self._nodes: dict[str, EvidenceNode] = {}
        self._edges: list[EvidenceEdge] = []

    def __len__(self) -> int:
        return len(self._nodes)

    @property
    def nodes(self) -> tuple[EvidenceNode, ...]:
        return tuple(self._nodes.values())

    @property
    def edges(self) -> tuple[EvidenceEdge, ...]:
        return tuple(self._edges)

    def add(
        self,
        kind: NodeKind,
        *,
        actor: str,
        payload: dict[str, Any] | None = None,
        observations: tuple[Observation, ...] | list[Observation] = (),
        confidence: float | None = None,
        node_id: str | None = None,
    ) -> EvidenceNode:
        """Append a node and return it.  The hash is computed here, once."""
        obs = tuple(observations)
        body = {
            "kind": str(kind),
            "payload": payload or {},
            "observations": [o.to_dict() for o in obs],
        }
        node = EvidenceNode(
            node_id=node_id or f"{kind.lower()}-{uuid.uuid4().hex[:12]}",
            transaction_id=self.transaction_id,
            kind=kind,
            actor=actor,
            created_at=utcnow(),
            payload=dict(payload or {}),
            observations=obs,
            confidence=confidence,
            node_hash=content_hash(body),
        )
        if node.node_id in self._nodes:
            raise ValueError(
                f"node {node.node_id} already exists (the graph is append-only)"
            )
        self._nodes[node.node_id] = node
        return node

    def link(
        self, src: str, dst: str, kind: EdgeKind, *, note: str = ""
    ) -> EvidenceEdge:
        for ref in (src, dst):
            if ref not in self._nodes:
                raise KeyError(f"unknown node {ref!r}")
        edge = EvidenceEdge(
            edge_id=f"edge-{uuid.uuid4().hex[:12]}",
            transaction_id=self.transaction_id,
            src=src,
            dst=dst,
            kind=kind,
            created_at=utcnow(),
            note=note,
        )
        self._edges.append(edge)
        return edge

    def get(self, node_id: str) -> EvidenceNode:
        return self._nodes[node_id]

    def of_kind(self, kind: NodeKind) -> tuple[EvidenceNode, ...]:
        return tuple(n for n in self._nodes.values() if n.kind == kind)

    def latest(self, kind: NodeKind) -> EvidenceNode | None:
        """Newest node of *kind*, skipping any that a later node supersedes."""
        superseded = {e.dst for e in self._edges if e.kind == EdgeKind.SUPERSEDES}
        live = [
            n
            for n in self._nodes.values()
            if n.kind == kind and n.node_id not in superseded
        ]
        if not live:
            return None
        return max(live, key=lambda n: n.created_at)

    def supports(self, node_id: str) -> tuple[EvidenceNode, ...]:
        """Nodes that directly support *node_id*."""
        return tuple(
            self._nodes[e.src]
            for e in self._edges
            if e.dst == node_id and e.kind == EdgeKind.SUPPORTS
        )

    def has_sandbox_evidence(self) -> bool:
        return any(n.is_sandbox for n in self._nodes.values())

    def reconstruct(self) -> dict[str, Any]:
        """The whole graph as plain data -- the dispute package's backbone."""
        return {
            "transaction_id": self.transaction_id,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
            "contains_sandbox_evidence": self.has_sandbox_evidence(),
        }
