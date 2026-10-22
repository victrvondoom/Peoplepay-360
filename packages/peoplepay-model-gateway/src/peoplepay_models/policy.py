"""The ONE central routing policy module. No routing preference lives anywhere else.

Everything here is data/config: thresholds, tier ordering per policy, privacy
admissibility by data class, fallback limits, timeouts per task class. User
preferences (stored per owner) override these defaults.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from .canonical import DataClass, FallbackMode, Privacy, RoutingPolicy
from .errors import ErrorCode, GatewayError

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
    daily_cost_limit: float | None = None    # currency units per rolling 24 h of KNOWN-price spend; None = no cap


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
    if isinstance(prefs.get("max_attempts"), int) and not isinstance(prefs.get("max_attempts"), bool) and 1 <= prefs["max_attempts"] <= 6:
        changes["max_attempts"] = prefs["max_attempts"]
    limit = prefs.get("daily_cost_limit")
    if isinstance(limit, (int, float)) and not isinstance(limit, bool) and math.isfinite(limit) and limit >= 0:
        changes["daily_cost_limit"] = float(limit)
    return replace(cfg, **changes)


# ---------------------------------------------------------------------------------------------------------------------
# Preference validation. A preference is stored per user and read on EVERY request, so one malformed value used to
# turn every later request for that user into a server error (``favorites: 5`` -> TypeError). Writes are validated here;
# reads go through ``sanitize_prefs`` so a value stored by an older version can never poison a request.
# ---------------------------------------------------------------------------------------------------------------------
_TIERS = ("fast", "balanced", "deep")
_MAX_ITEMS, _MAX_TEXT = 200, 200


def _enum_of(cls) -> Callable[[Any], Any]:
    values = [m.value for m in cls]

    def check(v):
        if not isinstance(v, str) or v not in values:
            raise ValueError("must be one of " + ", ".join(values))
        return v
    return check


def _one_of(*values: str) -> Callable[[Any], Any]:
    def check(v):
        if v not in values:
            raise ValueError("must be one of " + ", ".join(values))
        return v
    return check


def _bool(v):
    if not isinstance(v, bool):
        raise ValueError("must be true or false")
    return v


def _text_or_empty(v):
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > _MAX_TEXT:
        raise ValueError(f"must be text of at most {_MAX_TEXT} characters")
    return v


def _str_list(v):
    if (not isinstance(v, list) or len(v) > _MAX_ITEMS
            or not all(isinstance(x, str) and 0 < len(x) <= _MAX_TEXT for x in v)):
        raise ValueError(f"must be a list of at most {_MAX_ITEMS} short strings")
    return list(v)


def _str_map(value_check: Callable[[Any], Any] | None = None):
    def check(v):
        if not isinstance(v, dict) or len(v) > _MAX_ITEMS:
            raise ValueError(f"must be an object with at most {_MAX_ITEMS} entries")
        out = {}
        for k, x in v.items():
            if not isinstance(k, str) or not 0 < len(k) <= _MAX_TEXT:
                raise ValueError("keys must be short non-empty strings")
            out[k] = value_check(x) if value_check else x
        return out
    return check


def _short_str(v):
    if not isinstance(v, str) or not 0 < len(v) <= _MAX_TEXT:
        raise ValueError("must be a short non-empty string")
    return v


def _max_attempts(v):
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 6:
        raise ValueError("must be a whole number from 1 to 6")
    return v


def _cost_limit(v):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise ValueError("must be a finite number >= 0, or null for no limit")
    return v


def _tier(v):
    if v not in _TIERS:
        raise ValueError("must be one of " + ", ".join(_TIERS))
    return v


def _opt_preset(v):
    return None if v is None else _short_str(v)


_PREF_VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "routing_policy": _enum_of(RoutingPolicy),
    "fallback_mode": _enum_of(FallbackMode),
    "local_only": _bool,
    "default_model": _text_or_empty,
    "favorites": _str_list,
    "recent": _str_list,
    "preferred_routes": _str_list,
    "aliases": _str_map(_short_str),
    "model_tiers": _str_map(_tier),
    "allow_cloud_for_sensitive": _bool,
    "allow_auto_fallback_sensitive": _bool,
    "allow_unknown_price_fallback": _bool,
    "context_strategy": _one_of("trim", "summarize", "ask"),
    "max_attempts": _max_attempts,
    "daily_cost_limit": _cost_limit,
    "internal_models": _str_list,
    "capability_models": _str_map(_short_str),
    "preset": _opt_preset,
}


def validate_prefs(patch: Any) -> dict[str, Any]:
    """Validate a preference patch. Known keys are checked strictly and the cleaned values returned; unknown keys are
    ignored, as before. Raises ``GatewayError(INVALID_REQUEST)`` naming the offending key."""
    if not isinstance(patch, dict):
        raise GatewayError(ErrorCode.INVALID_REQUEST, "preferences must be a JSON object")
    out: dict[str, Any] = {}
    for key, value in patch.items():
        check = _PREF_VALIDATORS.get(key)
        if check is None:
            continue
        try:
            out[key] = check(value)
        except ValueError as exc:
            raise GatewayError(ErrorCode.INVALID_REQUEST, f"invalid preference {key!r}: {exc}") from None
    return out


def sanitize_prefs(raw: Any) -> dict[str, Any]:
    """Tolerant reader: keep every stored preference that is valid, drop the rest. Never raises."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        check = _PREF_VALIDATORS.get(key)
        if check is None:
            continue
        try:
            out[key] = check(value)
        except ValueError:
            continue
    return out
