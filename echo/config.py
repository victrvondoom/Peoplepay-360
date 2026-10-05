"""Central, explicit policy settings for the ECHO decision model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringConfig:
    correlated_observation_penalty: float = 3.0
    confidence_penalty_weight: float = 20.0
    minimum_provenance_roots: int = 2
    maximum_dependency_depth: int = 8
    robust_margin_for_fragile: float = 5.0


SCORING = ScoringConfig()
