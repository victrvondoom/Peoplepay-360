"""Auto router + candidate filtering with a full "why" trail.

Pure function over (requirements, routes, health, prefs). Nothing here names a model:
decisions read capabilities, privacy class, price, measured latency and user tiers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .canonical import (Capability as C, DataClass, FallbackMode, Health, InferenceRequest, ImagePart, FilePart,
                        Privacy, ProviderModelRoute, RoutingPolicy, ToolCallPart, ToolResultPart, Reasoning)
from .heuristics import tier_hint
from .health import HealthManager
from .policy import ADMISSIBLE, TIER_ORDER, OrgPolicy, RoutingConfig


@dataclass
class Requirements:
    caps: set[C] = field(default_factory=set)
    est_tokens: int = 0
    max_output: int = 0
    data_class: DataClass = DataClass.INTERNAL
    policy: RoutingPolicy = RoutingPolicy.BALANCED
    local_only: bool = False
    preferred_tier: str | None = None     # fast | balanced | deep | None
    task: str = "chat"
    explicit_route: str | None = None
    explicit_connection: str | None = None
    drop_unsupported: bool = False        # user consented to omit images/files the route cannot take
    reasons: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    route: ProviderModelRoute
    tier: str
    note: str = ""


@dataclass
class RoutePlan:
    ordered: list[Candidate]
    excluded: list[tuple[str, str]]       # (route label, reason)
    explanation: list[str]


def estimate_tokens(req: InferenceRequest) -> int:
    """Rough (chars/4, +800 per image). Flagged as an estimate wherever shown."""
    total = len(req.system or "") // 4
    for m in req.history():
        for p in m.parts:
            if hasattr(p, "text"):
                total += len(p.text) // 4 + 4
            elif isinstance(p, ImagePart):
                total += 800
            elif isinstance(p, FilePart):
                total += len(p.data_b64 or "") // 5
            else:
                total += len(str(getattr(p, "__dict__", ""))) // 4
    return total


def build_requirements(req: InferenceRequest, cfg: RoutingConfig, prefs: dict) -> Requirements:
    hist = req.history()
    kinds = {p.kind for m in hist for p in m.parts}
    r = Requirements(task=req.task, data_class=req.data_class, max_output=req.max_output_tokens or 0)
    r.drop_unsupported = bool(req.metadata.get("allow_drop_unsupported"))
    r.caps.add(C.TEXT)
    if "image" in kinds and not r.drop_unsupported:
        r.caps.add(C.VISION); r.reasons.append("Vision required: conversation contains images")
    if "file" in kinds and not r.drop_unsupported:
        r.caps.add(C.FILES); r.reasons.append("File input required: conversation contains files")
    if req.tools:
        r.caps.add(C.TOOLS); r.reasons.append("Tools required")
    if req.response_schema is not None:
        # Native support is not required: the gateway falls back to instruction + validation.
        r.reasons.append("Structured output required (validated)")
    if req.stream:
        r.caps.add(C.STREAMING)
    r.est_tokens = estimate_tokens(req)
    r.policy = req.routing_policy or cfg.default_policy
    sel = req.selection
    if sel.mode == "local" or r.policy == RoutingPolicy.LOCAL_ONLY or prefs.get("local_only"):
        r.local_only = True
        r.policy = RoutingPolicy.LOCAL_ONLY if r.policy != RoutingPolicy.LOCAL_ONLY else r.policy
        r.reasons.append("Local-only enabled: cloud routes excluded")
    if sel.mode in ("fast", "balanced", "deep"):
        r.preferred_tier = sel.mode
        r.reasons.append(f"User chose {sel.mode.title()} intelligence")
    elif sel.mode == "auto":
        last = next((m for m in reversed(hist) if m.role == "user"), None)
        chars = len(last.text) if last else 0
        if req.task in cfg.deep_tasks or req.reasoning == Reasoning.DEEP or r.est_tokens >= cfg.deep_min_est_tokens:
            r.preferred_tier = "deep"; r.reasons.append("Deep analysis task: preferring a reasoning-capable/larger model")
        elif req.reasoning == Reasoning.FAST or (chars <= cfg.simple_max_chars and not kinds - {"text"} and not req.tools):
            r.preferred_tier = "fast"; r.reasons.append("Simple request: preferring a fast model")
    if sel.model:
        r.explicit_route = sel.model
        r.explicit_connection = sel.connection_id
    if C.REASONING not in r.caps and r.preferred_tier == "deep" and req.reasoning == Reasoning.DEEP:
        r.reasons.append("Deep reasoning preference")
    return r


def tier_of(route: ProviderModelRoute, prefs: dict) -> str:
    user = (prefs.get("model_tiers") or {}).get(route.key) or (prefs.get("model_tiers") or {}).get(route.provider_model_id)
    if user in ("fast", "balanced", "deep"):
        return user
    if route.capabilities.has(C.REASONING) and not tier_hint(route.provider_model_id) == "fast":
        return "deep"
    return tier_hint(route.provider_model_id) or "balanced"


def _price(route: ProviderModelRoute) -> float | None:
    p = route.pricing or {}
    if "output_per_mtok" in p and "input_per_mtok" in p:
        return p["input_per_mtok"] + p["output_per_mtok"]
    return None


def plan_routes(reqs: Requirements, routes: list[ProviderModelRoute], *, health: HealthManager, prefs: dict,
                cfg: RoutingConfig, enabled_connections: set[str], org: OrgPolicy | None = None,
                exclude_keys: set[str] | None = None, label: Callable[[ProviderModelRoute], str] | None = None) -> RoutePlan:
    label = label or (lambda r: f"{r.display_name or r.provider_model_id} ({r.route})")
    excluded: list[tuple[str, str]] = []
    keep: list[Candidate] = []
    allowed_privacy = set(ADMISSIBLE[reqs.data_class])
    if reqs.data_class == DataClass.SENSITIVE and cfg.allow_cloud_for_sensitive:
        allowed_privacy.add(Privacy.CLOUD)
    if reqs.local_only:
        allowed_privacy = {Privacy.LOCAL}
    for r in routes:
        why = None
        if exclude_keys and r.key in exclude_keys:
            why = "already attempted"
        elif r.connection_id not in enabled_connections:
            why = "connection disabled"
        elif r.kind != "chat":
            why = f"not a chat model ({r.kind})"
        elif r.availability in ("unavailable", "deprecated"):
            why = f"model {r.availability}"
        elif reqs.explicit_connection and r.connection_id != reqs.explicit_connection:
            why = "different provider route than pinned"
        else:
            blocked, bwhy = health.blocked(r.connection_id, r.key)
            if blocked:
                why = bwhy
        if why is None:
            missing = [c.value for c in reqs.caps if not r.capabilities.has(c) and c != C.STREAMING]
            if missing:
                why = "lacks " + ", ".join(sorted(missing))
        if why is None and r.privacy not in allowed_privacy:
            why = ("local-only mode" if reqs.local_only else f"privacy: {reqs.data_class.value} data may not go to {r.privacy.value} routes")
        if why is None and org:
            why = org.allows(r.provider_id, r.connection_id, r.provider_model_id, r.privacy, r.region,
                             (r.pricing or {}).get("output_per_mtok"))
        tight = bool(r.context_window and reqs.est_tokens + reqs.max_output > r.context_window * cfg.context_safety)
        if why is None and tight and cfg.context_strategy == "ask":
            why = f"context too small ({r.context_window} tokens)"
        if why:
            excluded.append((label(r), why))
        else:
            keep.append(Candidate(r, tier_of(r, prefs), note="needs context trimming" if tight else ""))

    explicit_note = []
    if reqs.explicit_route:
        match = [c for c in keep if reqs.explicit_route in (c.route.key, c.route.provider_model_id, c.route.canonical_model_id)
                 or reqs.explicit_route == (prefs.get("aliases") or {}).get(c.route.key)]
        alias_target = (prefs.get("aliases") or {}).get(reqs.explicit_route)
        if alias_target:
            match = [c for c in keep if c.route.key == alias_target or c.route.provider_model_id == alias_target]
        keep_pinned = match
        if keep_pinned:
            explicit_note.append("User selected this model" + (" (pinned route)" if reqs.explicit_connection else ""))
            rest = [c for c in keep if c not in keep_pinned]
            keep = keep_pinned + _order(rest, reqs, health, prefs, cfg)
            keep_pinned_n = len(keep_pinned)
            return RoutePlan(keep, excluded, reqs.reasons + explicit_note + _why_first(keep[0], reqs, keep_pinned_n))
        reqs.reasons.append("Selected model is not usable for this request; falling back to routing")
    ordered = _order(keep, reqs, health, prefs, cfg)
    return RoutePlan(ordered, excluded, reqs.reasons + (_why_first(ordered[0], reqs, 0) if ordered else []))


def _why_first(c: Candidate, reqs: Requirements, pinned: int) -> list[str]:
    r = c.route
    out = [f"Selected {r.display_name or r.provider_model_id} via {r.route} ({c.tier} tier, {r.privacy.value})"]
    if reqs.policy != RoutingPolicy.BALANCED:
        out.append(f"Routing policy: {reqs.policy.value}")
    return out


def _order(cands: list[Candidate], reqs: Requirements, health: HealthManager, prefs: dict, cfg: RoutingConfig) -> list[Candidate]:
    preferred = list(prefs.get("preferred_routes") or [])
    favs = set(prefs.get("favorites") or [])
    tier_pref = ([reqs.preferred_tier] + [t for t in TIER_ORDER[reqs.policy] if t != reqs.preferred_tier]) \
        if reqs.preferred_tier else list(TIER_ORDER[reqs.policy])
    tier_rank = {t: i for i, t in enumerate(tier_pref)}
    state_rank = {Health.HEALTHY: 0, Health.UNKNOWN: 1, Health.DEGRADED: 2}

    def key(c: Candidate):
        r = c.route
        pref_rank = preferred.index(r.key) if r.key in preferred else len(preferred)
        st = state_rank.get(health.connection_state(r.connection_id), 3)
        lat = health.latency(r.connection_id, r.key)
        price = _price(r)
        lat_k = (lat is None, lat or 0.0)
        price_k = (0, 0.0) if r.local else ((price is None), price or 0.0)   # unknown price != free
        fav = 0 if r.key in favs else 1
        pol = reqs.policy
        if pol == RoutingPolicy.PRIVACY_FIRST:
            return (pref_rank, r.privacy.rank, tier_rank[c.tier], st, price_k, lat_k, fav)
        if pol == RoutingPolicy.FASTEST:
            return (pref_rank, tier_rank[c.tier], st, lat_k, price_k, fav)
        if pol == RoutingPolicy.LOW_COST:
            return (pref_rank, st, price_k, tier_rank[c.tier], lat_k, fav)
        if pol == RoutingPolicy.BEST_QUALITY:
            return (pref_rank, tier_rank[c.tier], st, -(r.context_window or 0), price_k, fav)
        return (pref_rank, tier_rank[c.tier], st, price_k if pol == RoutingPolicy.LOW_COST else lat_k, fav, -(r.context_window or 0))
    # A route that must trim history ranks after every route that fits as-is.
    return sorted(cands, key=lambda c: (bool(c.note), key(c)))
