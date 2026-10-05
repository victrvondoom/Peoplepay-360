"""Transparent robust-score and decision-fragility calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from echo.config import SCORING, ScoringConfig


@dataclass(frozen=True)
class CandidateScore:
    supplier_id: str
    supplier_name: str
    raw_score: float
    robust_score: float
    apparent_support_count: int
    provenance_root_count: int
    correlated_observation_count: int
    mean_confidence: float
    correlation_penalty: float
    confidence_penalty: float
    decision_status: str
    root_sources: tuple[str, ...]
    evidence_paths: tuple[dict[str, Any], ...]
    claim_ids: tuple[str, ...] = ()
    unresolved_provenance_count: int = 0
    identity_status: str = "MATCHED"
    policy_available: bool = True

    def to_dict(self) -> dict:
        result = asdict(self)
        result["root_sources"] = list(self.root_sources)
        result["evidence_paths"] = list(self.evidence_paths)
        return result


def robust_score(
    *,
    raw_score: float,
    apparent_support_count: int,
    provenance_root_count: int,
    mean_confidence: float,
    config: ScoringConfig = SCORING,
) -> tuple[float, float, float]:
    """Return score and separately explainable provenance/confidence penalties."""
    if not 0 <= raw_score <= 100:
        raise ValueError("raw score must be in [0, 100]")
    if apparent_support_count < 0 or provenance_root_count < 0:
        raise ValueError("support counts cannot be negative")
    if not 0 <= mean_confidence <= 1:
        raise ValueError("mean confidence must be in [0, 1]")
    correlated = max(0, apparent_support_count - provenance_root_count)
    correlation_penalty = config.correlated_observation_penalty * correlated
    confidence_penalty = config.confidence_penalty_weight * (1 - mean_confidence)
    return (
        round(max(0.0, min(100.0, raw_score - correlation_penalty - confidence_penalty)), 2),
        round(correlation_penalty, 2),
        round(confidence_penalty, 2),
    )


def fragility_class(winner_flip_count: int, root_removal_count: int,
                    margin: float, provenance_roots: int,
                    config: ScoringConfig = SCORING) -> str:
    if provenance_roots < config.minimum_provenance_roots:
        return "INSUFFICIENT_EVIDENCE"
    if winner_flip_count:
        return "FRAGILE"
    if root_removal_count and margin < config.robust_margin_for_fragile:
        return "MODERATELY_FRAGILE"
    return "ROBUST"
