"""Deterministic-first, cache-first, cost-aware explanation routing.

HONESTY NOTE. No paid model is called anywhere in the benchmark. ``SimulatedBackend`` is a seeded
stand-in whose prices, latencies and accuracies are ASSUMPTIONS (``ASSUMED_ILLUSTRATIVE``), swept in the
sensitivity experiment. What is genuinely measured from the real code paths: which tasks need a model
at all, prompt sizes (estimated as chars/4), cache hits, validator outcomes, and escalations. The
validator is a real deterministic check against the structured facts; the simulated model's *errors*
are deliberately realistic kinds (wrong supplier, wrong amount) so the validator has something to catch.
"""
from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import dataclass, field
from typing import Protocol

from .procurement import DecisionResult, Requirement

ASSUMED_ILLUSTRATIVE = True


@dataclass(frozen=True)
class ModelProfile:
    name: str
    price_in: float      # USD per 1M input tokens
    price_out: float     # USD per 1M output tokens
    ttft_s: float
    tps: float           # output tokens / second
    local: bool
    acc_easy: float      # P(valid explanation) on easy / hard decisions  (ASSUMPTION)
    acc_hard: float


DEFAULT_PROFILES = {
    "large": ModelProfile("large", 3.00, 15.00, 0.8, 60.0, False, 0.995, 0.95),
    "small": ModelProfile("small", 0.15, 0.60, 0.3, 150.0, False, 0.97, 0.55),
    # Local inference is not free: 0.05/0.20 is an ASSUMED amortized hardware+energy cost, not an API price.
    "local": ModelProfile("local", 0.05, 0.20, 0.5, 30.0, True, 0.93, 0.40),
}
INSTRUCTION = ("You are a procurement analyst. Explain the recommendation to a buyer in two sentences. "
               "State the winning supplier, its expected cost in INR, the margin over the runner-up, and any "
               "data-quality warning. Use only the facts provided.")
FLAW = " [flawed]"      # simulation device: an error the validator cannot see
MIN_OUT_TOKENS = 90      # ASSUMPTION: a model's prose is longer than our terse template


@dataclass(frozen=True)
class Facts:
    winner: str
    runner_up: str
    cost: float
    margin_pct: float
    flags: tuple[str, ...]


def facts_of(req: Requirement, res: DecisionResult) -> Facts:
    order = sorted(range(len(res.mean_cost)), key=lambda j: res.mean_cost[j])
    return Facts(req.suppliers[res.winner].id, req.suppliers[order[1]].id if len(order) > 1 else "-",
                 res.mean_cost[res.winner], res.margin * 100, res.quality_flags)


def render_explanation(f: Facts) -> str:
    warn = f" Warning: {', '.join(f.flags)}." if f.flags else ""
    return (f"Recommend {f.winner} at an expected INR {f.cost:,.0f}, {f.margin_pct:.1f}% below runner-up "
            f"{f.runner_up}.{warn}")


def validate_explanation(text: str, f: Facts) -> bool:
    """Deterministic check: names the right winner, quotes the cost within 0.5%, surfaces any quality flag."""
    import re
    if f.winner not in re.findall(r"\bS\d+\b", text.split("below")[0]):
        return False
    m = re.search(r"INR ([\d,]+)", text)
    if not m or abs(float(m.group(1).replace(",", "")) - f.cost) > 0.005 * f.cost:
        return False
    return all(flag.split(":")[0] in text for flag in f.flags)


def is_correct(text: str, f: Facts) -> bool:
    """Oracle used only by the benchmark (it knows the truth): validator AND no hidden flaw."""
    return validate_explanation(text, f) and FLAW not in text


def build_prompt(req: Requirement, res: DecisionResult, f: Facts, style: str) -> str:
    if style == "compact":
        return INSTRUCTION + "\nFACTS " + json.dumps([f.winner, f.runner_up, round(f.cost), round(f.margin_pct, 1), list(f.flags)])
    dump = {"requirement": {"id": req.id, "quantity": req.quantity, "period": req.period_now,
                            "suppliers": [{"id": s.id, "base_price": s.base_price, "currency": s.currency,
                                           "exposure": list(s.exposure)} for s in req.suppliers]},
            "analysis": {"mean_cost": res.mean_cost, "p90_cost": res.p90_cost, "margin": res.margin,
                         "p_not_best": res.p_not_best, "flags": list(res.quality_flags), "complete": res.complete}}
    return INSTRUCTION + "\nCONTEXT " + json.dumps(dump, indent=1)


def tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)          # chars/4 estimate, same for every configuration


@dataclass
class CallRecord:
    model: str
    local: bool
    in_tok: int
    out_tok: int
    cost: float
    latency_s: float
    valid: bool | None = None


class Backend(Protocol):
    def call(self, profile: ModelProfile, key: str, prompt: str, facts: Facts, hard: bool,
             local_only: bool = False) -> tuple[str, CallRecord]: ...


class SimulatedBackend:
    """Seeded stand-in for a model. Correct with probability acc (by difficulty); otherwise a realistic error."""

    def __init__(self, profiles=None, accuracy_override: dict | None = None, silent_error_share: float = 0.2):
        self.profiles = profiles or DEFAULT_PROFILES
        self.acc_override = accuracy_override or {}
        # Share of wrong outputs the deterministic validator CANNOT detect (e.g. an unsupported qualitative
        # claim). Real LLM failure modes are broader than "wrong number"; this keeps the validator honest.
        self.silent_error_share = silent_error_share

    def call(self, profile, key, prompt, facts, hard, local_only=False):
        acc = self.acc_override.get((profile.name, hard), profile.acc_hard if hard else profile.acc_easy)
        u = (zlib.crc32(f"{key}|{profile.name}".encode()) % 100_000) / 100_000
        if u < acc:
            text = render_explanation(facts)
        elif (zlib.crc32(f"{key}|v|{profile.name}".encode()) % 1000) / 1000 < self.silent_error_share:
            text = render_explanation(facts) + FLAW
        elif u % 2 < 1 and facts.runner_up != "-" and (zlib.crc32(key.encode()) & 1):
            text = render_explanation(Facts(facts.runner_up, facts.winner, facts.cost, facts.margin_pct, facts.flags))
        else:
            text = render_explanation(Facts(facts.winner, facts.runner_up, facts.cost * 1.08, facts.margin_pct, facts.flags))
        rec = self._record(profile, prompt, text)
        return text, rec

    @staticmethod
    def _record(profile, prompt, text):
        i, o = tokens(prompt), max(tokens(text), MIN_OUT_TOKENS)
        return CallRecord(profile.name, profile.local, i, o, (i * profile.price_in + o * profile.price_out) / 1e6,
                          profile.ttft_s + o / profile.tps)


@dataclass
class Config:
    name: str
    mode: str                          # single_large | static | adaptive
    prompt_style: str = "verbose"
    det_first: bool = False
    cache: bool = False
    validate_escalate: bool = False
    static_qty_threshold: int = 300    # mode=static only: a static feature, NOT evidence-based
    max_calls: int = 3


@dataclass
class Outcome:
    text: str
    verified: bool                     # passed the deterministic validator (or deterministic by construction)
    correct: bool                      # oracle: matches the true facts (known to the benchmark, not to the router)
    calls: list[CallRecord] = field(default_factory=list)
    cache_hit: bool = False
    path: str = ""
    privacy_violation: bool = False


class Router:
    def __init__(self, cfg: Config, backend: Backend | None = None, profiles=None):
        self.cfg, self.profiles = cfg, profiles or DEFAULT_PROFILES
        self.backend = backend or SimulatedBackend(self.profiles)
        self.cache: dict[str, str] = {}
        self.cache_lookups = 0

    @staticmethod
    def cache_key(f: Facts, data_class: str, style: str) -> str:
        return hashlib.sha256(json.dumps([f.winner, f.runner_up, round(f.cost), round(f.margin_pct, 1), f.flags,
                                          data_class, style, INSTRUCTION]).encode()).hexdigest()

    def _expected_cost(self, p: ModelProfile, prompt: str, hard: bool) -> float:
        acc = p.acc_hard if hard else p.acc_easy
        return (tokens(prompt) * p.price_in + MIN_OUT_TOKENS * p.price_out) / 1e6 / max(acc, 1e-3)

    def explain(self, req: Requirement, res: DecisionResult) -> Outcome:
        cfg, f = self.cfg, facts_of(req, res)
        truth = render_explanation(f)
        hard = res.hard
        local_only = req.data_class == "LOCAL_ONLY"
        prompt = build_prompt(req, res, f, cfg.prompt_style)
        key = f"{req.id}"

        if cfg.cache:
            self.cache_lookups += 1
            ck = self.cache_key(f, req.data_class, cfg.prompt_style)
            if ck in self.cache:
                t = self.cache[ck]
                return Outcome(t, True, is_correct(t, f), [], True, "cache")
        if cfg.det_first and not hard:
            out = Outcome(truth, True, True, [], False, "template")
            if cfg.cache:
                self.cache[ck] = truth
            return out

        if cfg.mode == "single_large":
            order = ["large"]
        elif cfg.mode == "static":
            order = ["local"] if local_only else ["large" if req.quantity >= cfg.static_qty_threshold else "small"]
        else:
            allowed = [p for p in self.profiles.values() if p.local] if local_only else list(self.profiles.values())
            order = [p.name for p in sorted(allowed, key=lambda p: self._expected_cost(p, prompt, hard))]
        calls: list[CallRecord] = []
        text, verified, path = "", False, ""
        for name in order[: cfg.max_calls]:
            prof = self.profiles[name]
            text, rec = self.backend.call(prof, key, prompt, f, hard, local_only)
            ok = validate_explanation(text, f)
            rec.valid = ok
            calls.append(rec)
            path += ("" if not path else ">") + name
            if not cfg.validate_escalate:
                verified = False
                break
            if ok:
                verified = True
                break
        if cfg.validate_escalate and not verified:
            text, verified, path = truth, True, path + ">template"      # last resort is deterministic, never unverified
        if cfg.cache and (verified or not cfg.validate_escalate):
            self.cache[ck] = text      # without validation there is nothing better to store (ablation of cache alone)
        violation = local_only and any(not c.local for c in calls)
        return Outcome(text, verified, is_correct(text, f), calls, False, path, violation)


class GatewayBackend:
    """Drives the real PeoplePay Model Gateway. ``routes`` maps profile name -> Gateway route key
    (``connection_id::provider_model_id``). Local-only work is sent as RESTRICTED data, so the Gateway itself
    refuses any non-local/non-organization route even if the router were wrong: defense in depth.
    Escalation stays in this router (Gateway fallback is switched off) so retries are not stacked."""

    def __init__(self, gateway, owner: str, routes: dict[str, str], profiles=None):
        self.gw, self.owner, self.routes = gateway, owner, routes
        self.profiles = profiles or DEFAULT_PROFILES

    def call(self, profile, key, prompt, facts, hard, local_only=False):
        from peoplepay_models.canonical import (DataClass, FallbackMode, InferenceRequest, Message, ModelSelection)
        from peoplepay_models.errors import GatewayError
        req = InferenceRequest(messages=[Message.user(prompt)], selection=ModelSelection("model", self.routes[profile.name], one_shot=True),
                               data_class=DataClass.RESTRICTED if local_only else DataClass.INTERNAL,
                               fallback_mode=FallbackMode.NONE, max_output_tokens=200, task="background",
                               metadata={"strict_selection": True})
        try:
            r = self.gw.infer(self.owner, req)
        except GatewayError as e:
            # A refused or failed call is a failed attempt, never a silent re-route.
            return "", CallRecord(profile.name, profile.local, tokens(prompt), 0, 0.0, 0.0, False)
        served = f"{r.served_by.connection_id}::{r.served_by.provider_model_id}"
        u = r.usage
        if served != self.routes[profile.name]:
            # Belt and braces: whatever served the call is what we account for, and it is never accepted as this profile's answer.
            return "", CallRecord(profile.name, profile.local, u.input_tokens or tokens(prompt), u.output_tokens or 0, 0.0, 0.0, False)
        cost = u.estimated_cost if u.estimated_cost is not None else 0.0      # unknown price is recorded as 0 AND flagged by callers
        return r.text, CallRecord(profile.name, profile.local, u.input_tokens or tokens(prompt), u.output_tokens or tokens(r.text),
                                  cost, (r.latency_ms or 0.0) / 1000)
