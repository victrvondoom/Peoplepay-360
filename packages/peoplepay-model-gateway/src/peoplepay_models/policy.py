"""The ONE central routing policy module. No routing preference lives anywhere else.

Everything here is data/config: thresholds, tier ordering per policy, privacy
admissibility by data class, fallback limits, timeouts per task class. User
preferences (stored per owner) override these defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .canonical import DataClass, FallbackMode, Privacy, RoutingPolicy

TIER_ORDER = {
    RoutingPolicy.BEST_QUALITY: ("deep", "balanced", "fast"),
    RoutingPolicy.BALANCED: ("balanced", "fast", "deep"),
    RoutingPolicy.FASTEST: ("fast", "balanced", "deep"),
    RoutingPolicy.LOW_COST: ("fast", "balanced", "deep"),
    RoutingPolicy.PRIVACY_FIRST: ("balanced", "fast", "deep"),
    RoutingPolicy.LOCAL_ONLY: ("balanced", "fast", "deep"),
    RoutingPolicy.CUSTOM: ("balanced", "fast", "deep"),
}

# Privacy classes a data classification may be sent to by default.
ADMISSIBLE = {
    DataClass.PUBLIC: {Privacy.LOCAL, Privacy.ORGANIZATION, Privacy.CLOUD},
    DataClass.INTERNAL: {Privacy.LOCAL, Privacy.ORGANIZATION, Privacy.CLOUD},
    DataClass.SENSITIVE: {Privacy.LOCAL, Privacy.ORGANIZATION},
    DataClass.RESTRICTED: {Privacy.LOCAL, Privacy.ORGANIZATION},
}

TIMEOUTS = {"chat": 60.0, "deep": 180.0, "vision": 90.0, "decision": 15.0, "background": 120.0}


@dataclass
class RoutingConfig:
    default_policy: RoutingPolicy = RoutingPolicy.BALANCED
    fallback_mode: FallbackMode = FallbackMode.AUTOMATIC
    max_attempts: int = 3
    cost_ceiling_ratio: float = 2.0          # LOW_COST fallbacks may not exceed this x the primary's price
    deep_tasks: tuple[str, ...] = ("analysis", "research", "reasoning", "evidence_research", "dispute_drafting")
    simple_max_chars: int = 400              # at/below this, with no attachments, Auto prefers the fast tier
    deep_min_est_tokens: int = 3000          # above this, Auto prefers the deep tier
    context_safety: float = 0.9              # use at most this share of a known context window
    context_strategy: str = "trim"           # trim | summarize | ask
    keep_recent_messages: int = 6
    decision_confidence_threshold: float = 0.7
    allow_cloud_for_sensitive: bool = False
    allow_auto_fallback_sensitive: bool = False
    allow_unknown_price_fallback: bool = False


@dataclass
class OrgPolicy:
    """Contract for future organization policy. Absent => no restriction."""
    allowed_providers: frozenset[str] | None = None
    denied_providers: frozenset[str] = frozenset()
    denied_models: frozenset[str] = frozenset()
    allowed_local_models: frozenset[str] | None = None
    no_external_cloud: bool = False
    allowed_regions: frozenset[str] | None = None
    max_price_per_mtok: float | None = None
    approved_connections: frozenset[str] | None = None

    def allows(self, provider_id: str, connection_id: str, model_id: str, privacy: Privacy,
               region: str | None, price_out: float | None) -> str | None:
        """Return a rejection reason, or None if allowed."""
        if self.allowed_providers is not None and provider_id not in self.allowed_providers:
            return "provider not allowed by organization policy"
        if provider_id in self.denied_providers:
            return "provider denied by organization policy"
        if model_id in self.denied_models:
            return "model denied by organization policy"
        if self.no_external_cloud and privacy == Privacy.CLOUD:
            return "organization policy forbids external cloud"
        if self.approved_connections is not None and privacy != Privacy.LOCAL and connection_id not in self.approved_connections:
            return "connection not approved by organization policy"
        if self.allowed_regions is not None and region and region not in self.allowed_regions:
            return "region not allowed by organization policy"
        if self.max_price_per_mtok is not None and price_out is not None and price_out > self.max_price_per_mtok:
            return "price above organization maximum"
        return None


# Built-in presets: policies, not model names.
PRESETS: dict[str, dict[str, Any]] = {
    "private_work": {"routing_policy": "PRIVACY_FIRST", "fallback_mode": "ASK"},
    "fast_chat": {"routing_policy": "FASTEST", "fallback_mode": "AUTOMATIC"},
    "deep_research": {"routing_policy": "BEST_QUALITY", "fallback_mode": "AUTOMATIC"},
    "low_cost": {"routing_policy": "LOW_COST", "fallback_mode": "AUTOMATIC"},
    "local_coding": {"routing_policy": "LOCAL_ONLY", "fallback_mode": "NONE"},
}


def config_with(prefs: dict[str, Any], base: RoutingConfig | None = None) -> RoutingConfig:
    cfg = base or RoutingConfig()
    changes: dict[str, Any] = {}
    if prefs.get("routing_policy"):
        try:
            changes["default_policy"] = RoutingPolicy(prefs["routing_policy"])
        except ValueError:
            pass
    if prefs.get("fallback_mode"):
        try:
            changes["fallback_mode"] = FallbackMode(prefs["fallback_mode"])
        except ValueError:
            pass
    for k in ("allow_cloud_for_sensitive", "allow_auto_fallback_sensitive", "allow_unknown_price_fallback"):
        if isinstance(prefs.get(k), bool):
            changes[k] = prefs[k]
    if prefs.get("context_strategy") in ("trim", "summarize", "ask"):
        changes["context_strategy"] = prefs["context_strategy"]
    if isinstance(prefs.get("max_attempts"), int) and 1 <= prefs["max_attempts"] <= 6:
        changes["max_attempts"] = prefs["max_attempts"]
    return replace(cfg, **changes)
