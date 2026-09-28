"""Build a decision-grade passport from transaction evidence.

The passport does not decide which product is best.  It answers a narrower and
safer question: whether every claim required for a consequential action is
present, fresh, sufficiently corroborated and non-conflicting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from beacon.assurance import (
    EdgeKind,
    EventKind,
    EvidenceClass,
    NodeKind,
    content_hash,
    utcnow,
)

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from beacon.assurance import Observation
    from beacon.peoplepay.transaction import Transaction

__all__ = [
    "ClaimCheck",
    "ClaimStatus",
    "EvidenceGate",
    "EvidencePassport",
    "EvidenceRequirement",
]

_EVIDENCE_ORDER = {
    EvidenceClass.UNAVAILABLE: 0,
    EvidenceClass.UNKNOWN: 1,
    EvidenceClass.CONFLICTING: 2,
    EvidenceClass.SANDBOX: 3,
    EvidenceClass.STALE: 4,
    EvidenceClass.UNVERIFIED: 5,
    EvidenceClass.VERIFIED: 6,
}


class ClaimStatus(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    field: str
    max_age: timedelta
    min_sources: int = 1
    require_verified: bool = True

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError("evidence requirement field is required")
        if self.max_age.total_seconds() <= 0:
            raise ValueError("evidence max_age must be positive")
        if self.min_sources < 1:
            raise ValueError("min_sources must be positive")


@dataclass(frozen=True, slots=True)
class ClaimCheck:
    field: str
    status: ClaimStatus
    evidence_class: EvidenceClass
    sources: tuple[str, ...]
    supporting_nodes: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "status": str(self.status),
            "evidence_class": str(self.evidence_class),
            "sources": list(self.sources),
            "supporting_nodes": list(self.supporting_nodes),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class EvidencePassport:
    transaction_id: str
    checks: tuple[ClaimCheck, ...]
    created_at: datetime = field(default_factory=utcnow)
    passport_hash: str = ""

    def __post_init__(self) -> None:
        if not self.checks:
            raise ValueError("an evidence passport needs at least one check")
        if not self.passport_hash:
            object.__setattr__(
                self,
                "passport_hash",
                content_hash(
                    {
                        "transaction_id": self.transaction_id,
                        "checks": [item.to_dict() for item in self.checks],
                        "created_at": self.created_at.isoformat(),
                    }
                ),
            )

    @property
    def decision_grade(self) -> bool:
        return all(item.status is ClaimStatus.PASS for item in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "decision_grade": self.decision_grade,
            "checks": [item.to_dict() for item in self.checks],
            "created_at": self.created_at.isoformat(),
            "passport_hash": self.passport_hash,
        }


@dataclass(frozen=True, slots=True)
class _Candidate:
    node_id: str
    observation: Observation


class EvidenceGate:
    """Evaluate requirements and append the resulting passport to the graph."""

    def evaluate(
        self,
        transaction: Transaction,
        requirements: tuple[EvidenceRequirement, ...],
        *,
        actor: str,
        now: datetime | None = None,
    ) -> EvidencePassport:
        if not requirements:
            raise ValueError("at least one evidence requirement is required")
        at = now or utcnow()
        checks = tuple(
            self._check(transaction, requirement, now=at)
            for requirement in requirements
        )
        passport = EvidencePassport(
            transaction_id=transaction.transaction_id,
            checks=checks,
            created_at=at,
        )
        node = transaction.graph.add(
            NodeKind.VERIFICATION,
            actor=actor,
            payload=passport.to_dict(),
        )
        support_ids = {
            node_id for check in checks for node_id in check.supporting_nodes
        }
        for supporting_node_id in sorted(support_ids):
            transaction.graph.link(
                supporting_node_id,
                node.node_id,
                EdgeKind.SUPPORTS,
                note="supports evidence passport",
            )
        transaction.ledger.append(
            EventKind.VERIFICATION_RUN,
            actor=actor,
            detail={
                "passport_hash": passport.passport_hash,
                "node_id": node.node_id,
                "decision_grade": passport.decision_grade,
                "blocked_fields": [
                    item.field for item in checks if item.status is ClaimStatus.BLOCK
                ],
            },
        )
        return passport

    def _check(
        self,
        transaction: Transaction,
        requirement: EvidenceRequirement,
        *,
        now: datetime,
    ) -> ClaimCheck:
        candidates = [
            _Candidate(node.node_id, observation.aged(requirement.max_age, now=now))
            for node in transaction.graph.nodes
            for observation in node.observations
            if observation.field == requirement.field
        ]
        if not candidates:
            return ClaimCheck(
                field=requirement.field,
                status=ClaimStatus.BLOCK,
                evidence_class=EvidenceClass.UNKNOWN,
                sources=(),
                supporting_nodes=(),
                reason="required claim has not been observed",
            )

        values = {
            content_hash(
                item.observation.normalized_value
                if item.observation.normalized_value is not None
                else item.observation.value
            )
            for item in candidates
            if item.observation.evidence_class
            in (EvidenceClass.VERIFIED, EvidenceClass.UNVERIFIED)
        }
        sources = tuple(
            sorted({item.observation.provenance.source for item in candidates})
        )
        node_ids = tuple(sorted({item.node_id for item in candidates}))
        if len(values) > 1 or any(
            item.observation.evidence_class is EvidenceClass.CONFLICTING
            for item in candidates
        ):
            return ClaimCheck(
                field=requirement.field,
                status=ClaimStatus.BLOCK,
                evidence_class=EvidenceClass.CONFLICTING,
                sources=sources,
                supporting_nodes=node_ids,
                reason="sources disagree on the required claim",
            )

        eligible = [
            item
            for item in candidates
            if item.observation.evidence_class
            in (EvidenceClass.VERIFIED, EvidenceClass.UNVERIFIED)
            and (
                not requirement.require_verified
                or item.observation.evidence_class is EvidenceClass.VERIFIED
            )
        ]
        eligible_sources = tuple(
            sorted({item.observation.provenance.source for item in eligible})
        )
        if len(eligible_sources) < requirement.min_sources:
            weakest = min(
                (item.observation.evidence_class for item in candidates),
                key=_EVIDENCE_ORDER.__getitem__,
            )
            return ClaimCheck(
                field=requirement.field,
                status=ClaimStatus.BLOCK,
                evidence_class=weakest,
                sources=sources,
                supporting_nodes=node_ids,
                reason=(
                    f"needs {requirement.min_sources} eligible source(s), "
                    f"found {len(eligible_sources)}"
                ),
            )

        evidence_class = (
            EvidenceClass.VERIFIED
            if all(
                item.observation.evidence_class is EvidenceClass.VERIFIED
                for item in eligible
            )
            else EvidenceClass.UNVERIFIED
        )
        return ClaimCheck(
            field=requirement.field,
            status=ClaimStatus.PASS,
            evidence_class=evidence_class,
            sources=eligible_sources,
            supporting_nodes=tuple(sorted({item.node_id for item in eligible})),
            reason="claim is fresh, consistent and sufficiently corroborated",
        )
