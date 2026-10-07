"""ModelGateway: connections, discovery, routing, fallback, conversations, usage.

Owns provider integration, model selection, inference, fallback, capability detection,
health, usage and stream normalization, and credential routing. It does NOT own trust,
evidence or authorization (ECHO and the PeoplePay Gateway do): a model's output can
never authorize a payment, order, submission or operational change.
"""
from __future__ import annotations

import threading
import time
from dataclasses import replace
from typing import Any, Iterator

from . import usage as usage_mod
from .adapters.base import AdapterResult, CallSpec, DecisionProvider, ProviderAdapter, ProviderManifest
from .canonical import (Capability as C, Conversation, DataClass, DecisionAnswer, DecisionQuestion, Evidence,
                        FallbackMode, FilePart, Health, ImagePart, InferenceRequest, InferenceResponse, Message,
                        ModelSelection, Attempt, Privacy, ProviderConnection, ProviderModelRoute, ProviderType,
                        Reasoning, RoutingPolicy, ServedBy, StreamEvent, StructuredPart, TextPart, ToolCallPart,
                        ToolDefinition, ToolResultPart, Usage, new_id, now)
from .errors import ErrorCode, GatewayError, redact
from .health import HealthManager
from .netguard import NetPolicy, validate_url
from .policy import OrgPolicy, PRESETS, RoutingConfig, TIMEOUTS, config_with
from .registry import ModelRegistry, ProviderRegistry, default_registry
from .router import Requirements, RoutePlan, build_requirements, estimate_tokens, plan_routes, tier_of
from .schema import parse_and_validate
from .store import ModelStore
from .transport import HttpTransport, Transport
from .vault import MemoryVault, Vault

SYSTEM_OWNER = "system"
_SENSITIVE = (DataClass.SENSITIVE, DataClass.RESTRICTED)


class CancelToken:
    def __init__(self) -> None:
        self._e = threading.Event()

    def cancel(self) -> None:
        self._e.set()

    @property
    def cancelled(self) -> bool:
        return self._e.is_set()


def _label(r: ProviderModelRoute) -> str:
    return f"{r.display_name or r.provider_model_id} ({r.route})"


class ModelGateway:
    def __init__(self, store: ModelStore | None = None, vault: Vault | None = None, transport: Transport | None = None,
                 registry: ProviderRegistry | None = None, config: RoutingConfig | None = None,
                 org_policy: OrgPolicy | None = None, net_policy: NetPolicy | None = None,
                 health: HealthManager | None = None, catalog_ttl: float = 6 * 3600.0,
                 adapter_kwargs: dict[str, dict] | None = None):
        self.store = store or ModelStore()
        self.vault = vault or MemoryVault()
        self.system_vault = MemoryVault()    # env-derived secrets: process lifetime only, never persisted
        self.net = net_policy or NetPolicy.from_env()
        self.transport = transport or HttpTransport(self.net)
        self.providers = registry or default_registry()
        self.models = ModelRegistry(self.store, ttl=catalog_ttl)
        self.health_mgr = health or HealthManager()
        self.config = config or RoutingConfig()
        self.org_policy = org_policy
        self.adapter_kwargs = adapter_kwargs or {}   # per provider id, e.g. Bedrock client_factory (tests)
        self.metrics: dict[str, int] = {}
        self.disabled_models: set[str] = set()
        self.vault_persistent = not isinstance(self.vault, MemoryVault)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers
    def _inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.metrics[name] = self.metrics.get(name, 0) + n

    @staticmethod
    def scope_of(owner: str) -> str:
        return f"user:{owner}"

    def visible_scopes(self, owner: str, orgs: list[str] | None = None) -> list[str]:
        return [SYSTEM_OWNER, self.scope_of(owner), *[f"org:{o}" for o in orgs or []]]

    def connections(self, owner: str, orgs: list[str] | None = None) -> list[ProviderConnection]:
        return [c for c in self.store.list_connections(self.visible_scopes(owner, orgs)) if self.providers.is_enabled(c.provider_type)]

    def _conn(self, owner: str, cid: str) -> ProviderConnection:
        c = self.store.get_connection(cid)
        if c is None or c.owner_scope not in self.visible_scopes(owner):
            raise GatewayError(ErrorCode.INVALID_REQUEST, "connection not found")   # same answer for foreign ids
        return c

    def _writable(self, owner: str, cid: str) -> ProviderConnection:
        c = self._conn(owner, cid)
        if c.owner_scope != self.scope_of(owner):
            raise GatewayError(ErrorCode.AUTHORIZATION_REQUIRED, "this connection is managed by the platform or organization")
        return c

    def _secrets(self, c: ProviderConnection) -> dict[str, str]:
        if not c.credential_ref:
            return {}
        if c.system:
            return self.system_vault.reveal(SYSTEM_OWNER, c.credential_ref)
        return self.vault.reveal(c.owner_scope, c.credential_ref)

    def adapter(self, c: ProviderConnection):
        try:
            secrets = self._secrets(c)
        except Exception:
            raise GatewayError(ErrorCode.INVALID_CREDENTIALS, "stored credential is unavailable; re-enter it") from None
        return self.providers.build(c, secrets, self.transport, **self.adapter_kwargs.get(c.provider_type, {}))

    # ------------------------------------------------------------------ connections (BYOK)
    def provider_catalog(self) -> list[dict]:
        return [m.public() for m in self.providers.manifests()]

    def vault_status(self) -> dict:
        return {"persistent": self.vault_persistent,
                "note": "Credentials are encrypted at rest." if self.vault_persistent else
                        "Credentials are held in memory only and will be lost on restart. Set PEOPLEPAY_MODELS_VAULT_KEY to persist them encrypted."}

    def _split_fields(self, m: ProviderManifest, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        config: dict[str, Any] = {}
        secrets: dict[str, str] = {}
        known = {f.name: f for f in m.fields}
        for name, val in (values or {}).items():
            if name in ("headers", "capability_overrides", "manual_models", "models_endpoint", "paths", "script", "models",
                        "offline", "local", "call_tool", "tool_args", "bad_tool_call", "structured_reply", "retry_after",
                        "max_tokens_param", "stream_usage", "route_label"):
                if name in ("script", "models", "offline", "local", "call_tool", "tool_args", "bad_tool_call", "structured_reply", "retry_after") and m.id != "mock":
                    continue
                config[name] = val
                continue
            f = known.get(name)
            if f is None:
                continue                      # unknown fields are dropped, not stored
            if f.secret:
                if val not in (None, ""):
                    secrets[name] = str(val)
            elif val not in (None, ""):
                config[name] = val
        for f in m.fields:
            if f.required and not f.secret and f.name not in config and f.default is None and m.id != "mock":
                raise GatewayError(ErrorCode.INVALID_REQUEST, f"{f.label} is required")
            if f.required and f.secret and f.name not in secrets:
                raise GatewayError(ErrorCode.INVALID_REQUEST, f"{f.label} is required")
            if f.default is not None and f.name not in config and not f.secret:
                config[f.name] = f.default
        if config.get("privacy") not in (None, "local", "organization", "cloud"):
            raise GatewayError(ErrorCode.INVALID_REQUEST, "invalid data boundary")
        return config, secrets

    def _check_url(self, m: ProviderManifest, config: dict[str, Any]) -> None:
        url = config.get("base_url")
        if not url:
            return
        validate_url(url, self.net)    # raises CUSTOM_ENDPOINT_BLOCKED; re-checked, IP-pinned, on every request

    def connect(self, owner: str, provider_type: str, display_name: str, values: dict[str, Any], *,
                alias: str | None = None, test: bool = True) -> dict:
        m = self.providers.manifest(provider_type)
        if not self.providers.is_enabled(provider_type):
            raise GatewayError(ErrorCode.POLICY_REJECTED, "this provider is disabled on this platform")
        config, secrets = self._split_fields(m, values)
        if self.net.mode == "cloud" and config.get("privacy") == "local" and provider_type != "ollama":
            config["privacy"] = "organization"
        self._check_url(m, config)
        owner_scope = self.scope_of(owner)
        ref = self.vault.put(owner_scope, secrets) if secrets else None
        conn = ProviderConnection(id=new_id("conn"), provider_type=provider_type,
                                  display_name=display_name.strip()[:80] or m.display_name,
                                  owner_scope=owner_scope, configuration=config, credential_ref=ref, alias=alias)
        self.store.save_connection(conn)
        out = {"connection": conn.public()}
        if test:
            out["test"] = self.test_connection(owner, conn.id)
        return out

    def update_connection(self, owner: str, cid: str, *, display_name: str | None = None, enabled: bool | None = None,
                          values: dict[str, Any] | None = None) -> dict:
        c = self._writable(owner, cid)
        if display_name is not None:
            c.display_name = display_name.strip()[:80] or c.display_name
        if enabled is not None:
            c.enabled = enabled
            if not enabled:
                self.health_mgr.disable(cid)
            else:
                self.health_mgr.set_probe(cid, Health.UNKNOWN, None)
        if values:
            m = self.providers.manifest(c.provider_type)
            merged = {**c.configuration, **values}
            sec_names = {f.name for f in m.fields if f.secret}
            new_secrets = {k: v for k, v in values.items() if k in sec_names and v}
            config = {k: v for k, v in merged.items() if k not in sec_names}
            self._check_url(m, config)
            c.configuration = config
            if new_secrets:
                old = self.vault.reveal(c.owner_scope, c.credential_ref) if c.credential_ref else {}
                if c.credential_ref:
                    self.vault.delete(c.owner_scope, c.credential_ref)
                c.credential_ref = self.vault.put(c.owner_scope, {**old, **new_secrets})
            c.validation_status = "not_validated"
        self.store.save_connection(c)
        return c.public()

    def remove_connection(self, owner: str, cid: str) -> None:
        c = self._writable(owner, cid)
        if c.credential_ref:
            self.vault.delete(c.owner_scope, c.credential_ref)
        self.store.delete_connection(cid)
        # NOTE: past messages keep their served_by record (provider/model/route as strings), so history survives.

    def register_system_connection(self, cid: str, provider_type: str, display_name: str, config: dict[str, Any],
                                   secrets: dict[str, str]) -> ProviderConnection:
        ref = self.system_vault.put(SYSTEM_OWNER, secrets) if secrets else None
        existing = self.store.get_connection(cid)
        conn = ProviderConnection(id=cid, provider_type=provider_type, display_name=display_name,
                                  owner_scope=SYSTEM_OWNER, configuration=config, credential_ref=ref, system=True,
                                  enabled=existing.enabled if existing else True,
                                  created_at=existing.created_at if existing else now())
        self.store.save_connection(conn)
        return conn

    # ------------------------------------------------------------------ test / health / discovery
    def test_connection(self, owner: str, cid: str) -> dict:
        c = self._conn(owner, cid)
        try:
            ad = self.adapter(c)
            rep = ad.validate_credentials()
        except GatewayError as e:
            self.health_mgr.record_failure(cid, cid, e)
            return {"ok": False, "state": self.health_mgr.connection_state(cid).value, "error": e.to_dict()}
        self.health_mgr.set_probe(cid, rep.state, rep.latency_ms, rep.detail)
        ok = rep.state == Health.HEALTHY
        if c.owner_scope == self.scope_of(owner) or c.system:
            c.last_validated_at = now()
            c.validation_status = "ok" if ok else "invalid"
            self.store.save_connection(c)
        out: dict[str, Any] = {"ok": ok, "state": rep.state.value, "latency_ms": rep.latency_ms, "detail": rep.detail}
        if ok:
            try:
                out["models_found"] = len(self.refresh_models(owner, cid)["models"])
            except GatewayError as e:
                out["discovery_error"] = e.to_dict()
        return out

    def refresh_models(self, owner: str, cid: str) -> dict:
        c = self._conn(owner, cid)
        if not c.enabled:
            raise GatewayError(ErrorCode.POLICY_REJECTED, "connection is disabled")
        try:
            routes = self.adapter(c).discover_models()
        except GatewayError as e:
            self.models.store.get_catalog(cid)   # keep any previous catalog
            self.health_mgr.record_failure(cid, cid, e)
            prev = self.models.get(cid)
            if prev:
                self.models.store.save_catalog(cid, prev, e.code.value)
            raise
        for r in routes:
            r.connection_id = cid
            if f"{r.provider_id}:{r.provider_model_id}" in self.disabled_models:
                r.availability = "unavailable"; r.status = "disabled by platform owner"
        self.models.put(cid, routes)
        return {"connection_id": cid, "models": [r.to_dict() for r in self.models.get(cid)], "refreshed_at": now()}

    def refresh_stale(self, owner: str) -> dict[str, str]:
        """Scheduled/manual maintenance: refresh only catalogs older than the TTL."""
        res = {}
        for c in self.connections(owner):
            if c.enabled and self.models.is_stale(c.id):
                try:
                    self.refresh_models(owner, c.id); res[c.id] = "refreshed"
                except GatewayError as e:
                    res[c.id] = e.code.value
        return res

    def test_capability(self, owner: str, cid: str, provider_model_id: str, cap: C) -> dict:
        """Explicit capability test (user action). Success upgrades evidence to CAPABILITY_TEST."""
        c = self._conn(owner, cid)
        routes = {r.provider_model_id: r for r in self.models.get(cid)}
        r = routes.get(provider_model_id)
        if r is None:
            raise GatewayError(ErrorCode.MODEL_NOT_FOUND, "model not in catalog; refresh first")
        png = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        probes = {
            C.VISION: dict(messages=[Message("user", [ImagePart("image/png", png), TextPart("Reply with the word ok.")])]),
            C.TOOLS: dict(messages=[Message.user("Call the ping tool.")],
                          tools=[ToolDefinition("ping", "Responds pong", {"type": "object", "properties": {}})]),
            C.STRUCTURED_OUTPUT: dict(messages=[Message.user('Return {"ok": true} as JSON.')],
                                      response_schema={"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}),
        }
        if cap not in probes:
            raise GatewayError(ErrorCode.INVALID_REQUEST, f"no test available for {cap.value}")
        spec = CallSpec(provider_model_id=provider_model_id, max_output_tokens=64, timeout=45.0, caps=r.capabilities, **probes[cap])
        ok = False
        try:
            res = self.adapter(c).generate(spec)
            if cap == C.TOOLS:
                ok = any(isinstance(p, ToolCallPart) for p in res.parts)
            elif cap == C.STRUCTURED_OUTPUT:
                text = "".join(p.text for p in res.parts if isinstance(p, TextPart))
                ok = not parse_and_validate(text, probes[cap]["response_schema"])[1]
            else:
                ok = bool(res.parts)
        except GatewayError as e:
            return {"ok": False, "capability": cap.value, "error": e.to_dict()}
        if ok:
            r.capabilities.add(cap, Evidence.CAPABILITY_TEST)
            self.models.store.save_catalog(cid, list(routes.values()))
        return {"ok": ok, "capability": cap.value, "evidence": Evidence.CAPABILITY_TEST.value if ok else None}

    def health_overview(self, owner: str) -> list[dict]:
        out = []
        for c in self.connections(owner):
            m = self.providers.manifest(c.provider_type)
            snap = self.health_mgr.snapshot(c.id) if c.enabled else {"state": Health.DISABLED.value}
            age = self.models.age(c.id)
            routes = self.models.get(c.id)
            status = self._status_label(c, snap)
            out.append({"connection": c.public(), "provider": {"id": m.id, "name": m.display_name, "type": m.type.value,
                                                                "kind": m.kind, "local": m.local, "route_label": m.route_label,
                                                                "verification": m.verification, "experimental": m.experimental},
                        "status": status, "health": snap, "models_found": len(routes),
                        "catalog_age_s": round(age, 1) if age is not None else None,
                        "catalog_error": self.models.last_error(c.id), "notice": m.notice})
        return out

    @staticmethod
    def _status_label(c: ProviderConnection, snap: dict) -> str:
        if not c.enabled:
            return "Disabled"
        st = snap.get("state")
        if c.validation_status == "invalid" and st in (None, "UNKNOWN", "AUTH_ERROR"):
            return "Invalid credentials" if st == "AUTH_ERROR" else "Unavailable"
        return {"HEALTHY": "Connected", "DEGRADED": "Degraded", "RATE_LIMITED": "Rate limited", "AUTH_ERROR": "Invalid credentials",
                "UNAVAILABLE": "Unavailable", "DISABLED": "Disabled", "UNKNOWN": "Not validated" if c.validation_status == "not_validated" else "Connected"}.get(st, "Unknown")

    def service_health(self) -> dict:
        conns = self.store.list_connections()
        healthy = sum(1 for c in conns if c.enabled and self.health_mgr.connection_state(c.id) == Health.HEALTHY)
        ages = [a for a in (self.models.age(c.id) for c in conns) if a is not None]
        return {"status": "ok", "providers_registered": len(self.providers.manifests()), "connections": len(conns),
                "connected": healthy, "oldest_catalog_age_s": round(max(ages), 1) if ages else None,
                "metrics": dict(self.metrics)}

    # ------------------------------------------------------------------ preferences
    def get_prefs(self, owner: str) -> dict:
        return self.store.get_prefs(owner)

    def set_prefs(self, owner: str, patch: dict[str, Any]) -> dict:
        allowed = {"routing_policy", "fallback_mode", "local_only", "default_model", "favorites", "recent", "aliases",
                   "model_tiers", "preferred_routes", "allow_cloud_for_sensitive", "allow_auto_fallback_sensitive",
                   "allow_unknown_price_fallback", "context_strategy", "max_attempts", "daily_cost_limit", "internal_models",
                   "preset", "capability_models"}
        prefs = self.store.get_prefs(owner)
        for k, v in patch.items():
            if k in allowed:
                prefs[k] = v
        if "routing_policy" in patch and patch["routing_policy"] not in [p.value for p in RoutingPolicy]:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "unknown routing policy")
        if "fallback_mode" in patch and patch["fallback_mode"] not in [p.value for p in FallbackMode]:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "unknown fallback mode")
        self.store.save_prefs(owner, prefs)
        return prefs

    def apply_preset(self, owner: str, name: str) -> dict:
        if name not in PRESETS:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "unknown preset")
        p = dict(PRESETS[name]); p["preset"] = name
        p["local_only"] = p["routing_policy"] == "LOCAL_ONLY"
        return self.set_prefs(owner, p)

    def export_prefs(self, owner: str) -> dict:
        """Non-secret preferences only. Connections and credentials are never exported."""
        return {"version": 1, "preferences": self.store.get_prefs(owner)}

    def import_prefs(self, owner: str, blob: dict) -> dict:
        if not isinstance(blob, dict) or not isinstance(blob.get("preferences"), dict):
            raise GatewayError(ErrorCode.INVALID_REQUEST, "invalid preferences export")
        return self.set_prefs(owner, blob["preferences"])

    # ------------------------------------------------------------------ catalog views
    def _chat_routes(self, owner: str) -> tuple[list[ProviderModelRoute], set[str]]:
        conns = self.connections(owner)
        enabled = {c.id for c in conns if c.enabled}
        routes = [r for c in conns if c.enabled for r in self.models.get(c.id)]
        return routes, enabled

    def list_models(self, owner: str, *, q: str | None = None, caps: list[str] | None = None, provider: str | None = None,
                    local: bool | None = None, kind: str | None = None, include_unavailable: bool = False) -> dict:
        prefs = self.store.get_prefs(owner)
        favs = set(prefs.get("favorites") or [])
        conns = {c.id: c for c in self.connections(owner)}
        rows = []
        for cid, c in conns.items():
            if not c.enabled:
                continue
            for r in self.models.get(cid):
                if kind and r.kind != kind:
                    continue
                if not kind and r.kind not in ("chat", "decision"):
                    continue
                if not include_unavailable and r.availability in ("unavailable", "deprecated"):
                    continue
                if provider and r.provider_id != provider:
                    continue
                if local is not None and r.local != local:
                    continue
                if caps and not all(r.capabilities.has(C(x)) for x in caps if x in C._value2member_map_):
                    continue
                text = f"{r.display_name} {r.provider_model_id} {r.provider_id} {r.route}".lower()
                if q and q.lower() not in text:
                    continue
                d = r.to_dict()
                d.update(tier=tier_of(r, prefs) if r.kind == "chat" else None, favorite=r.key in favs,
                         health=self.health_mgr.connection_state(cid).value, connection_name=c.alias or c.display_name,
                         selectable_as_chat=r.kind == "chat")
                rows.append(d)
        groups: dict[str, dict] = {}
        for d in rows:
            g = groups.setdefault(d["canonical_model_id"], {"canonical_model_id": d["canonical_model_id"],
                                                             "display_name": d["display_name"], "kind": d["kind"], "routes": []})
            g["routes"].append(d)
        return {"models": rows, "groups": list(groups.values()), "count": len(rows),
                "recent": prefs.get("recent") or [], "favorites": sorted(favs)}

    # ------------------------------------------------------------------ planning
    def plan(self, owner: str, req: InferenceRequest, exclude: set[str] | None = None, *, _prefs: dict | None = None) -> tuple[RoutePlan, Requirements, RoutingConfig]:
        prefs = _prefs if _prefs is not None else self.store.get_prefs(owner)
        cfg = config_with(prefs, self.config)
        self._apply_default(req, prefs)
        reqs = build_requirements(req, cfg, prefs)
        routes, enabled = self._chat_routes(owner)
        plan = plan_routes(reqs, routes, health=self.health_mgr, prefs=prefs, cfg=cfg, enabled_connections=enabled,
                           org=self.org_policy, exclude_keys=exclude, label=_label)
        return plan, reqs, cfg

    @staticmethod
    def _apply_default(req: InferenceRequest, prefs: dict) -> None:
        """``mode == "default"`` means "whatever the user set as their default"; an explicit Auto stays Auto."""
        sel = req.selection
        if sel.mode == "default":
            dm = prefs.get("default_model")
            if dm:
                sel.mode, sel.model = "model", dm
            else:
                sel.mode = "auto"
        elif sel.mode == "model" and not sel.model:
            sel.mode = "auto"

    def explain(self, owner: str, req: InferenceRequest) -> dict:
        """Developer-mode 'Why this model?': requirements, considered, chosen, excluded."""
        plan, reqs, cfg = self.plan(owner, req)
        return {"requirements": sorted(c.value for c in reqs.caps), "policy": reqs.policy.value, "local_only": reqs.local_only,
                "data_class": reqs.data_class.value, "est_tokens": reqs.est_tokens, "token_estimate_note": "estimate (chars/4)",
                "explanation": plan.explanation, "considered": [_label(c.route) for c in plan.ordered],
                "selected": _label(plan.ordered[0].route) if plan.ordered else None,
                "excluded": [{"model": a, "reason": b} for a, b in plan.excluded]}

    # ------------------------------------------------------------------ message adaptation
    def _adapt(self, history: list[Message], route: ProviderModelRoute, reqs: Requirements, has_tools: bool) -> tuple[list[Message], list[str]]:
        notes: list[str] = []
        out: list[Message] = []
        flatten_tools = not route.capabilities.has(C.TOOLS) or not has_tools
        dropped_img = dropped_file = flat = 0
        for m in history:
            parts = []
            for p in m.parts:
                if isinstance(p, ImagePart) and not route.capabilities.has(C.VISION):
                    if not reqs.drop_unsupported:
                        raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, "this model cannot process images in the conversation",
                                           extra={"needs_consent": "drop_images"})
                    parts.append(TextPart("[image omitted: this model cannot process images]")); dropped_img += 1
                elif isinstance(p, FilePart) and not route.capabilities.has(C.FILES):
                    if not reqs.drop_unsupported:
                        raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, "this model cannot process file attachments in the conversation",
                                           extra={"needs_consent": "drop_files"})
                    parts.append(TextPart(f"[file {p.name!r} omitted]")); dropped_file += 1
                elif isinstance(p, ToolCallPart) and flatten_tools:
                    parts.append(TextPart(f"[tool call {p.name}({p.arguments})]")); flat += 1
                elif isinstance(p, ToolResultPart) and flatten_tools:
                    parts.append(TextPart(f"[tool result: {p.content}]")); flat += 1
                else:
                    parts.append(p)
            out.append(Message(m.role if not (flatten_tools and m.role == "tool") else "user", parts, m.id, m.created_at, m.served_by, m.metadata))
        if dropped_img:
            notes.append(f"{dropped_img} image(s) omitted with your consent")
        if dropped_file:
            notes.append(f"{dropped_file} file(s) omitted with your consent")
        if flat:
            notes.append("earlier tool calls were converted to text for this model")
        return out, notes

    def _fit_context(self, owner: str, msgs: list[Message], route: ProviderModelRoute, cfg: RoutingConfig,
                     req: InferenceRequest) -> tuple[list[Message], list[str]]:
        if not route.context_window:
            return msgs, []
        limit = int(route.context_window * cfg.context_safety) - (req.max_output_tokens or 0)
        probe = replace(req, conversation=None, messages=msgs)
        if estimate_tokens(probe) <= limit:
            return msgs, []
        opts = {"options": ["choose a longer-context model", "start a new conversation", "allow trimming older messages"],
                "context_window": route.context_window}
        if cfg.context_strategy == "ask":
            raise GatewayError(ErrorCode.CONTEXT_TOO_LARGE, "conversation exceeds the model's context window", extra=opts)
        keep = cfg.keep_recent_messages
        head = [m for m in msgs if m.role == "system"]
        body = [m for m in msgs if m.role != "system"]
        recent, older = body[-keep:], body[:-keep]
        if not older or estimate_tokens(replace(req, conversation=None, messages=head + recent)) > limit:
            raise GatewayError(ErrorCode.CONTEXT_TOO_LARGE, "the most recent messages alone exceed the model's context window", extra=opts)
        # drop oldest as few as needed
        kept_older = list(older)
        while kept_older and estimate_tokens(replace(req, conversation=None, messages=head + kept_older + recent)) > limit:
            kept_older.pop(0)
        dropped = older[: len(older) - len(kept_older)]
        notes = [f"context trimmed: {len(dropped)} earlier message(s) omitted"]
        summary: list[Message] = []
        if cfg.context_strategy == "summarize" and dropped:
            try:
                s = self.summarize(owner, dropped)
                summary = [Message("user", [TextPart(f"[Summary of earlier conversation: {s}]")])]
                notes = [f"context summarized: {len(dropped)} earlier message(s) condensed"]
            except GatewayError:
                pass
        return head + summary + kept_older + recent, notes

    def summarize(self, owner: str, msgs: list[Message]) -> str:
        text = "\n".join(f"{m.role}: {m.text}" for m in msgs)[:12000]
        r = self.infer(owner, InferenceRequest(
            messages=[Message.user("Summarize this conversation excerpt in under 150 words, keeping facts, decisions and open questions:\n" + text)],
            selection=ModelSelection("fast"), task="background", max_output_tokens=300))
        return r.text

    # ------------------------------------------------------------------ core run loop
    def _cost_ok(self, primary: ProviderModelRoute | None, cand: ProviderModelRoute, reqs: Requirements, cfg: RoutingConfig) -> bool:
        if reqs.policy != RoutingPolicy.LOW_COST or primary is None or cand.local:
            return True
        pp = (primary.pricing or {}).get("output_per_mtok")
        cp = (cand.pricing or {}).get("output_per_mtok")
        if pp is None:
            return True
        if cp is None:
            return cfg.allow_unknown_price_fallback
        return cp <= pp * cfg.cost_ceiling_ratio

    def _requested_label(self, req: InferenceRequest) -> str:
        """Human label for what the user asked for (never an internal route key)."""
        s = req.selection
        if not s.model:
            return "Auto" if s.mode == "auto" else s.mode.title()
        cid, _, mid = s.model.partition("::")
        if mid:
            for r in self.models.get(cid):
                if r.provider_model_id == mid:
                    return r.display_name or mid
            return mid
        return s.model

    def _no_route_error(self, owner: str, plan: RoutePlan, reqs: Requirements, req: InferenceRequest) -> GatewayError:
        reasons = [b for _, b in plan.excluded]
        details = {"excluded": [{"model": a, "reason": b} for a, b in plan.excluded][:20]}
        if reqs.local_only:
            locals_ = [c for c in self.connections(owner) if self.providers.manifest(c.provider_type).local and c.enabled]
            if locals_ or not any(True for _ in self.connections(owner)):
                return GatewayError(ErrorCode.LOCAL_PROVIDER_OFFLINE, "Local-only is on and no local model is available. "
                                    "PeoplePay will not send this request to a cloud provider.",
                                    extra={**details, "ask_privacy_change": True})
            return GatewayError(ErrorCode.LOCAL_PROVIDER_OFFLINE, "Local-only is on but no local provider is connected.",
                                extra={**details, "ask_privacy_change": True})
        if any("privacy" in r for r in reasons) and len(reasons) and all(("privacy" in r or "lacks" in r or "organization policy" in r) for r in reasons):
            return GatewayError(ErrorCode.PRIVACY_POLICY_BLOCKED, "No allowed route for this data classification.", extra=details)
        if any("lacks" in r for r in reasons):
            capable = [a for a, b in plan.excluded if "lacks" not in b]
            miss = sorted({c.value for c in reqs.caps} - {"text"})
            return GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, "No connected model supports: " + ", ".join(miss),
                                extra={**details, **({"needs_consent": "drop_images"} if C.VISION in reqs.caps else {})})
        return GatewayError(ErrorCode.NO_ROUTE, "No connected model is available. Connect a provider or configure a local model.", extra=details)

    def _run(self, owner: str, req: InferenceRequest, cancel: CancelToken | None, streaming: bool) -> Iterator[tuple[str, Any]]:
        cancel = cancel or CancelToken()
        plan, reqs, cfg = self.plan(owner, req)
        if not plan.ordered:
            self._inc("no_route")
            raise self._no_route_error(owner, plan, reqs, req)
        mode = req.fallback_mode or cfg.fallback_mode
        if reqs.data_class in _SENSITIVE and mode == FallbackMode.AUTOMATIC and not cfg.allow_auto_fallback_sensitive:
            mode = FallbackMode.ASK
        attempts: list[Attempt] = []
        visited: set[str] = set()
        primary: ProviderModelRoute | None = None
        parent_inv: str | None = None
        fallback_reason: str | None = None
        history = req.history()
        has_tools = bool(req.tools)
        timeout = TIMEOUTS.get("deep" if reqs.preferred_tier == "deep" else "vision" if C.VISION in reqs.caps else "chat")
        queue = list(plan.ordered)
        last_err: GatewayError | None = None
        while queue:
            if cancel.cancelled:
                raise GatewayError(ErrorCode.CANCELLED, "cancelled")
            if len(attempts) >= cfg.max_attempts:
                break
            cand = queue.pop(0)
            r = cand.route
            if r.key in visited:
                continue
            if primary is not None and not self._cost_ok(primary, r, reqs, cfg):
                attempts.append(Attempt(r.key, r.provider_id, r.provider_model_id, "skipped", reason="exceeds low-cost ceiling"))
                continue
            blocked, why = self.health_mgr.blocked(r.connection_id, r.key)
            if blocked:
                attempts.append(Attempt(r.key, r.provider_id, r.provider_model_id, "skipped", reason=why))
                continue
            visited.add(r.key)
            primary = primary or r
            inv_id = new_id("inv")
            t0 = time.perf_counter()
            started = now()
            try:
                conn = self.store.get_connection(r.connection_id)
                if conn is None or not conn.enabled:
                    raise GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, "connection unavailable")
                msgs, adapt_notes = self._adapt(history, r, reqs, has_tools)
                msgs, ctx_notes = self._fit_context(owner, msgs, r, cfg, req)
                system, schema, extra_notes = req.system, req.response_schema, []
                if schema is not None and not r.capabilities.has(C.STRUCTURED_OUTPUT):
                    import json as _j
                    system = ((system or "") + "\n\nRespond with ONLY a JSON value matching this JSON Schema:\n" + _j.dumps(schema)).strip()
                    schema = None; extra_notes.append("structured output via instruction + gateway validation")
                spec = CallSpec(provider_model_id=r.provider_model_id, messages=msgs, system=system, tools=req.tools,
                                response_schema=schema, temperature=req.temperature, max_output_tokens=req.max_output_tokens,
                                reasoning=req.reasoning, provider_options=req.provider_options, timeout=timeout, caps=r.capabilities)
                adapter = self.adapter(conn)
                parts_text: list[str] = []
                result: AdapterResult
                if streaming:
                    emitted = False
                    tool_parts: list[ToolCallPart] = []
                    usage_ev, done_ev = {}, {}
                    buffered: list[StreamEvent] = []
                    try:
                        for ev in adapter.stream(spec):
                            if cancel.cancelled:
                                raise GatewayError(ErrorCode.CANCELLED, "cancelled")
                            if ev.type == "response.started":
                                buffered.append(ev); continue
                            if ev.type == "text.delta":
                                if buffered:
                                    for b in buffered:
                                        yield "event", b
                                    buffered = []
                                emitted = True
                                parts_text.append(ev.data.get("text", ""))
                                yield "event", ev
                            elif ev.type == "tool.completed":
                                tool_parts.append(ToolCallPart(ev.data["call_id"], ev.data["name"], ev.data["arguments"]))
                                if buffered:
                                    for b in buffered:
                                        yield "event", b
                                    buffered = []
                                emitted = True
                                yield "event", ev
                            elif ev.type == "tool.started":
                                yield "event", ev
                            elif ev.type == "usage":
                                usage_ev = ev.data
                            elif ev.type == "response.completed":
                                done_ev = ev.data
                    except GatewayError as e:
                        e.extra["partial_output"] = emitted     # mid-stream failures cannot be transparently retried
                        if emitted:
                            self._record(owner, req, r, inv_id, parent_inv, "error", started, t0, Usage(), e.code.value)
                            self.health_mgr.record_failure(r.connection_id, r.key, e)
                            attempts.append(Attempt(r.key, r.provider_id, r.provider_model_id, "error", e.code.value, (time.perf_counter() - t0) * 1000))
                            e.extra["attempts"] = [a.__dict__ for a in attempts]
                            raise
                        raise
                    text_all = "".join(parts_text)
                    out_parts: list[Any] = ([TextPart(text_all)] if text_all else []) + tool_parts
                    result = AdapterResult(out_parts, Usage(usage_ev.get("input_tokens"), usage_ev.get("output_tokens"),
                                                            usage_ev.get("cached_tokens"), usage_ev.get("cost")),
                                           done_ev.get("finish_reason"), done_ev.get("model_used"), None, list(done_ev.get("notes") or []))
                else:
                    result = adapter.generate(spec)
                # validate structured output
                if req.response_schema is not None and not any(isinstance(p, ToolCallPart) for p in result.parts):
                    text = "".join(p.text for p in result.parts if isinstance(p, TextPart))
                    data, errs = parse_and_validate(text, req.response_schema)
                    if errs:
                        raise GatewayError(ErrorCode.INVALID_RESPONSE, "structured output failed validation: " + "; ".join(errs[:3]))
                    result.parts = [StructuredPart(data)]
                if not result.parts:
                    raise GatewayError(ErrorCode.INVALID_RESPONSE, "empty response")
            except GatewayError as e:
                last_err = e
                lat = (time.perf_counter() - t0) * 1000
                if e.code != ErrorCode.CANCELLED:
                    self.health_mgr.record_failure(r.connection_id, r.key, e)
                self._record(owner, req, r, inv_id, parent_inv, "error", started, t0, Usage(), e.code.value)
                attempts.append(Attempt(r.key, r.provider_id, r.provider_model_id, "error", e.code.value, lat))
                self._inc(f"errors.{r.provider_id}")
                if e.code == ErrorCode.RATE_LIMITED:
                    self._inc("rate_limits")
                e.extra["attempts"] = [a.__dict__ for a in attempts]
                if e.extra.get("partial_output") or e.code == ErrorCode.CANCELLED or not e.fallback_eligible or mode == FallbackMode.NONE:
                    raise
                if mode == FallbackMode.ASK:
                    alts = [{"route_key": c.route.key, "label": _label(c.route), "privacy": c.route.privacy.value}
                            for c in queue if self._cost_ok(primary, c.route, reqs, cfg)][:5]
                    if not alts:
                        raise
                    e.extra.update(ask_before_switching=True, alternatives=alts, failed_route=_label(r))
                    raise
                parent_inv, fallback_reason = inv_id, e.code.value
                self._inc("fallbacks")
                continue
            # success
            lat = (time.perf_counter() - t0) * 1000
            usage = result.usage
            usage.estimated_cost = usage.estimated_cost if usage.estimated_cost is not None else self._cost(r, usage)
            self.health_mgr.record_success(r.connection_id, r.key, lat)
            self._record(owner, req, r, inv_id, parent_inv, "ok", started, t0, usage, None)
            attempts.append(Attempt(r.key, r.provider_id, r.provider_model_id, "ok", None, lat))
            self._inc(f"requests.{r.provider_id}")
            if r.local:
                self._inc("local_requests")
            served = ServedBy(provider_id=r.provider_id, connection_id=r.connection_id, model_id=r.canonical_model_id,
                              provider_model_id=r.provider_model_id, route=r.route, requested=self._requested_label(req),
                              fallback_reason=fallback_reason)
            if result.served_via:
                served.route = f"{r.route} → {result.served_via}"
            expl = list(plan.explanation)
            if fallback_reason:
                expl.append(f"Fallback used because the earlier route failed: {fallback_reason}")
            resp = InferenceResponse(result.parts, self._requested_label(req), served, usage, lat, result.finish_reason, attempts,
                                     expl, adapt_notes + ctx_notes + extra_notes + result.notes, inv_id)
            if r.pricing is None and not r.local and usage.estimated_cost is None:
                resp.notes.append("cost unknown: no reliable pricing for this route")
            self._remember_recent(owner, req, r)
            yield "done", resp
            return
        if last_err is not None:
            last_err.extra["attempts"] = [a.__dict__ for a in attempts]
            raise last_err
        err = GatewayError(ErrorCode.NO_ROUTE, "every candidate route was unavailable", extra={"attempts": [a.__dict__ for a in attempts]})
        raise err

    def _cost(self, r: ProviderModelRoute, u: Usage) -> float | None:
        p = r.pricing
        if not p or u.input_tokens is None or u.output_tokens is None:
            return None
        try:
            return (u.input_tokens * p["input_per_mtok"] + u.output_tokens * p["output_per_mtok"]) / 1e6
        except KeyError:
            return None

    def _record(self, owner, req, r, inv_id, parent, status, started, t0, usage: Usage, error_class) -> None:
        # Operational metadata only: no prompt or completion text is ever written here.
        self.store.record_invocation({
            "id": inv_id, "owner": owner, "conversation_id": req.conversation.id if req.conversation else req.metadata.get("conversation_id"),
            "connection_id": r.connection_id, "provider_id": r.provider_id, "model_id": r.provider_model_id, "route": r.route,
            "status": status, "started_at": started, "ended_at": now(), "latency_ms": (time.perf_counter() - t0) * 1000,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cached_tokens": usage.cached_tokens,
            "est_cost": usage.estimated_cost, "fallback_parent": parent, "error_class": error_class, "task": req.task, "local": int(r.local)})

    def _remember_recent(self, owner: str, req: InferenceRequest, r: ProviderModelRoute) -> None:
        if req.selection.one_shot:
            return
        prefs = self.store.get_prefs(owner)
        rec = [k for k in (prefs.get("recent") or []) if k != r.key]
        prefs["recent"] = ([r.key] + rec)[:8]
        self.store.save_prefs(owner, prefs)

    # ------------------------------------------------------------------ public inference API
    def infer(self, owner: str, req: InferenceRequest, cancel: CancelToken | None = None) -> InferenceResponse:
        resp = None
        for kind, val in self._run(owner, req, cancel, streaming=False):
            if kind == "done":
                resp = val
        assert resp is not None
        self._enforce_cost_limit_note(owner, resp)
        return resp

    def stream(self, owner: str, req: InferenceRequest, cancel: CancelToken | None = None) -> Iterator[StreamEvent]:
        """Canonical stream events. Provider framing never escapes the adapters."""
        try:
            for kind, val in self._run(owner, req, cancel, streaming=True):
                if kind == "event":
                    yield val
                else:
                    resp: InferenceResponse = val
                    yield StreamEvent("usage", {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
                                                "cached_tokens": resp.usage.cached_tokens, "estimated_cost": resp.usage.estimated_cost})
                    yield StreamEvent("response.completed", {"response": resp.to_dict()})
        except GatewayError as e:
            yield StreamEvent("error", e.to_dict())

    def _enforce_cost_limit_note(self, owner: str, resp: InferenceResponse) -> None:
        limit = self.store.get_prefs(owner).get("daily_cost_limit")
        if isinstance(limit, (int, float)):
            spent = sum(r["est_cost"] or 0 for r in self.store.usage_rows(owner, now() - 86400))
            if spent >= limit:
                resp.notes.append(f"daily cost limit reached (known costs only: {spent:.4f})")

    # ------------------------------------------------------------------ conversations
    def new_conversation(self, owner: str, title: str = "") -> Conversation:
        c = Conversation(owner=owner, title=title)
        self.store.save_conversation(c)
        return c

    def get_conversation(self, owner: str, cid: str) -> Conversation:
        c = self.store.get_conversation(cid, owner)
        if c is None:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "conversation not found")
        return c

    def check_switch(self, owner: str, conversation_id: str, selection: ModelSelection) -> dict:
        """Preview what changing the model mid-conversation would do. Never silently drops content."""
        conv = self.get_conversation(owner, conversation_id)
        warnings = []
        routes, _ = self._chat_routes(owner)
        target = next((r for r in routes if selection.model in (r.key, r.provider_model_id, r.canonical_model_id)), None)
        if selection.model and target is None:
            return {"ok": False, "warnings": [{"code": "MODEL_NOT_FOUND", "message": "That model is not available."}]}
        kinds = conv.required_input_kinds()
        if target:
            if "image" in kinds and not target.capabilities.has(C.VISION):
                warnings.append({"code": "IMAGES_UNSUPPORTED", "message": "This model cannot process images from this conversation.",
                                 "options": ["choose another model", "continue without image context"],
                                 "alternatives": [_label(r) for r in routes if r.capabilities.has(C.VISION) and r.kind == "chat"][:5]})
            if "file" in kinds and not target.capabilities.has(C.FILES):
                warnings.append({"code": "FILES_UNSUPPORTED", "message": "This model cannot process file attachments from this conversation."})
            if target.context_window and estimate_tokens(InferenceRequest(conversation=conv)) > target.context_window * self.config.context_safety:
                warnings.append({"code": "CONTEXT_LARGE", "message": "The conversation may not fit this model's context window."})
        return {"ok": not any(w["code"].endswith("UNSUPPORTED") for w in warnings), "warnings": warnings,
                "message": f"Future replies will use {_label(target) if target else selection.mode.title()}."}

    def chat(self, owner: str, text: str, *, conversation_id: str | None = None, attachments: list | None = None,
             selection: ModelSelection | None = None, **kw) -> dict:
        conv = self.get_conversation(owner, conversation_id) if conversation_id else Conversation(owner=owner, title=text[:60])
        user_msg = Message("user", [TextPart(text), *(attachments or [])])
        req = InferenceRequest(conversation=Conversation(conv.id, owner, conv.title, conv.messages + [user_msg]),
                               selection=selection or ModelSelection(), **kw)
        resp = self.infer(owner, req)
        conv.add(user_msg)
        conv.add(resp.to_message())
        self.store.save_conversation(conv)
        return {"conversation_id": conv.id, "message": conv.messages[-1].to_dict(), "response": resp.to_dict()}

    def chat_stream(self, owner: str, text: str, *, conversation_id: str | None = None, attachments: list | None = None,
                    selection: ModelSelection | None = None, cancel: CancelToken | None = None, **kw) -> Iterator[StreamEvent]:
        try:
            conv = self.get_conversation(owner, conversation_id) if conversation_id else Conversation(owner=owner, title=text[:60])
        except GatewayError as e:
            yield StreamEvent("error", e.to_dict()); return
        user_msg = Message("user", [TextPart(text), *(attachments or [])])
        req = InferenceRequest(conversation=Conversation(conv.id, owner, conv.title, conv.messages + [user_msg]),
                               selection=selection or ModelSelection(), stream=True, **kw)
        for ev in self.stream(owner, req, cancel):
            if ev.type == "response.completed":
                rd = ev.data["response"]
                from .canonical import ServedBy as SB
                msg = Message("assistant", [TextPart(rd["text"])] if rd["text"] else [], served_by=SB(**rd["served_by"]),
                              metadata={"invocation_id": rd["invocation_id"], "notes": rd["notes"]})
                for p in rd["parts"]:
                    if p.get("kind") == "tool_call":
                        msg.parts.append(ToolCallPart(p["call_id"], p["name"], p["arguments"]))
                conv.add(user_msg); conv.add(msg)
                self.store.save_conversation(conv)
                ev.data["conversation_id"] = conv.id
                ev.data["message"] = msg.to_dict()
            yield ev

    # ------------------------------------------------------------------ decision models
    def _decision_routes(self, owner: str, kind: str) -> list[tuple[ProviderConnection, ProviderModelRoute]]:
        out = []
        for c in self.connections(owner):
            if not c.enabled or self.providers.manifest(c.provider_type).kind != "decision":
                continue
            blocked, _ = self.health_mgr.blocked(c.id, c.id)
            if blocked:
                continue
            for r in self.models.get(c.id):
                if r.capabilities.has({"BOOLEAN": C.DECISION_BOOLEAN, "CHOICE": C.DECISION_CHOICE}.get(kind, C.DECISION_SCORE)) or not r.capabilities.items:
                    out.append((c, r))
        return out

    def decide(self, owner: str, state: dict, questions: list[DecisionQuestion], *, local_only: bool = False,
               model: str | None = None) -> dict:
        """Typed fast decision. Decision providers never produce prose and never authorize actions."""
        prefs = self.store.get_prefs(owner)
        local_only = local_only or bool(prefs.get("local_only"))
        kinds = {q.kind for q in questions}
        cands = self._decision_routes(owner, next(iter(kinds)) if len(kinds) == 1 else "SCORE")
        if local_only:
            cands = [(c, r) for c, r in cands if r.privacy == Privacy.LOCAL]
        if model:
            cands = [(c, r) for c, r in cands if model in (r.key, r.provider_model_id)]
        if not cands:
            raise GatewayError(ErrorCode.NO_ROUTE, "no decision model is connected" + (" within the local-only boundary" if local_only else ""))
        last: GatewayError | None = None
        for c, r in cands[: self.config.max_attempts]:
            t0, started, inv = time.perf_counter(), now(), new_id("inv")
            try:
                prov = self.adapter(c)
                answers = prov.decide(r.provider_model_id, state, questions, TIMEOUTS["decision"])
                self.health_mgr.record_success(c.id, r.key, (time.perf_counter() - t0) * 1000)
                self._record(owner, InferenceRequest(task="decision"), r, inv, None, "ok", started, t0, Usage(), None)
                return {"answers": [a.__dict__ for a in answers], "served_by": {"provider_id": r.provider_id, "model": r.provider_model_id, "route": r.route},
                        "origin": "MODEL_INFERENCE"}
            except GatewayError as e:
                last = e
                self.health_mgr.record_failure(c.id, r.key, e)
                self._record(owner, InferenceRequest(task="decision"), r, inv, None, "error", started, t0, Usage(), e.code.value)
                if not e.fallback_eligible:
                    raise
        raise last or GatewayError(ErrorCode.NO_ROUTE, "no decision model answered")

    def decide_or_escalate(self, owner: str, questions: list[DecisionQuestion], state: dict, escalation: InferenceRequest,
                           *, threshold: float | None = None) -> dict:
        """Fast typed path when confident; otherwise a generative/reasoning route. Records which path ran."""
        cfg = config_with(self.store.get_prefs(owner), self.config)
        threshold = cfg.decision_confidence_threshold if threshold is None else threshold
        try:
            dec = self.decide(owner, state, questions, local_only=escalation.selection.mode == "local")
        except GatewayError as e:
            if e.code not in (ErrorCode.NO_ROUTE, ErrorCode.INVALID_RESPONSE, ErrorCode.TIMEOUT, ErrorCode.PROVIDER_UNAVAILABLE,
                              ErrorCode.RATE_LIMITED, ErrorCode.SERVER_ERROR):
                raise
            dec, why = None, f"decision model unavailable: {e.code.value}"
        else:
            confs = [a["confidence"] for a in dec["answers"]]
            why = None if all(c is not None and c >= threshold for c in confs) else "confidence below threshold or not reported"
        if dec is not None and why is None:
            return {"path": "fast_decision", "decision": dec, "escalated": False}
        escalation.selection = escalation.selection if escalation.selection.mode != "auto" else ModelSelection("deep")
        return {"path": "escalated", "reason": why, "decision": dec, "response": self.infer(owner, escalation).to_dict(), "escalated": True}

    # ------------------------------------------------------------------ provenance for ECHO
    @staticmethod
    def provenance(resp: InferenceResponse, *, source: str) -> dict:
        """Attach to any AI-derived claim entering ECHO. A model assertion is MODEL_INFERENCE, never SOURCE_EVIDENCE."""
        s = resp.served_by
        return {"origin": "MODEL_INFERENCE", "provider": s.provider_id, "model": s.provider_model_id, "route": s.route,
                "timestamp": now(), "source": source, "invocation_id": resp.invocation_id}

    def usage(self, owner: str, since: float | None = None) -> dict:
        data = usage_mod.aggregate(self.store, owner, since)
        names = {c.id: (c.alias or c.display_name) for c in self.connections(owner)}
        for cid, v in data["providers"].items():
            v["connection_name"] = names.get(cid, cid)
        return data
