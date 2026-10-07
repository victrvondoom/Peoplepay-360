"""Provider adapter contract + manifest.

Adding a provider = one adapter + one manifest + contract tests + docs. Nothing in
routing, fallback or UI changes: they read manifests and capabilities.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from ..canonical import (Capability, CapabilitySet, DecisionAnswer, DecisionQuestion, Evidence, Health,
                         Message, ProviderModelRoute, ProviderType, Privacy, ToolDefinition, Usage,
                         StreamEvent, Part, Reasoning)
from ..errors import ErrorCode, GatewayError
from ..heuristics import infer_capabilities, infer_kind
from ..transport import Transport


@dataclass
class CredentialField:
    name: str
    label: str
    secret: bool = False
    required: bool = True
    default: str | None = None
    help: str = ""
    options: list[str] | None = None


@dataclass
class ProviderManifest:
    id: str
    display_name: str
    type: ProviderType
    protocols: tuple[str, ...]
    fields: tuple[CredentialField, ...]          # drives the BYOK form; secrets stay server-side
    discovery_mode: str                           # dynamic | static | manual | hybrid
    route_label: str
    privacy: Privacy = Privacy.CLOUD
    local: bool = False
    default_base_url: str | None = None
    kind: str = "chat"                            # chat | decision
    notice: str = ""                              # shown before connecting
    experimental: bool = False
    supports_streaming: bool = True
    # Which capabilities this provider can possibly expose; informational.
    capabilities_hint: tuple[Capability, ...] = ()
    verification: str = "contract"                # what the repo can honestly claim: mock|contract|live

    def public(self) -> dict:
        return {"id": self.id, "display_name": self.display_name, "type": self.type.value,
                "protocols": list(self.protocols), "discovery_mode": self.discovery_mode,
                "route_label": self.route_label, "privacy": self.privacy.value, "local": self.local,
                "default_base_url": self.default_base_url, "kind": self.kind, "notice": self.notice,
                "experimental": self.experimental,
                "fields": [{"name": f.name, "label": f.label, "secret": f.secret, "required": f.required,
                            "default": f.default, "help": f.help, "options": f.options} for f in self.fields]}


@dataclass
class CallSpec:
    """Everything an adapter needs for one call; already capability-checked by the gateway."""
    provider_model_id: str
    messages: list[Message]
    system: str | None = None
    tools: list[ToolDefinition] = field(default_factory=list)
    response_schema: dict | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    reasoning: Reasoning = Reasoning.AUTO
    provider_options: dict[str, Any] = field(default_factory=dict)
    timeout: float = 60.0
    caps: CapabilitySet = field(default_factory=CapabilitySet)   # for param mapping decisions


@dataclass
class AdapterResult:
    parts: list[Part]
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None
    model_used: str | None = None          # what the provider says served it (may differ)
    served_via: str | None = None          # e.g. OpenRouter's upstream provider
    notes: list[str] = field(default_factory=list)


@dataclass
class HealthReport:
    state: Health
    latency_ms: float | None = None
    detail: str = ""
    checked_at: float = field(default_factory=time.time)


class ProviderAdapter:
    manifest: ProviderManifest

    def __init__(self, connection_id: str, config: dict[str, Any], secrets: dict[str, str],
                 transport: Transport):
        self.connection_id = connection_id
        self.config = config
        self.secrets = secrets
        self.transport = transport

    # -- required
    def provider_metadata(self) -> dict:
        return self.manifest.public()

    def health(self) -> HealthReport:
        raise NotImplementedError

    def discover_models(self) -> list[ProviderModelRoute]:
        raise NotImplementedError

    def get_model_metadata(self, model_id: str) -> ProviderModelRoute | None:
        for r in self.discover_models():
            if r.provider_model_id == model_id:
                return r
        return None

    def generate(self, spec: CallSpec) -> AdapterResult:
        raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, f"{self.manifest.id} does not generate text")

    def stream(self, spec: CallSpec) -> Iterator[StreamEvent]:
        raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, f"{self.manifest.id} does not stream")

    def validate_credentials(self) -> HealthReport:
        h = self.health()
        return h

    # -- optional
    def count_tokens(self, spec: CallSpec) -> int | None:
        return None

    def normalize_usage(self, raw: dict | None) -> Usage:
        return Usage()

    def normalize_error(self, exc: Exception) -> GatewayError:
        if isinstance(exc, GatewayError):
            return exc
        return GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, f"{type(exc).__name__}")

    # -- helpers
    def route(self, provider_model_id: str, *, display_name: str = "", caps: CapabilitySet | None = None,
              **kw) -> ProviderModelRoute:
        m = self.manifest
        kind = kw.pop("kind", None) or infer_kind(provider_model_id)
        if caps is None:
            caps = CapabilitySet()
            if kind == "chat":
                caps.add(Capability.TEXT, Evidence.STATIC_FALLBACK)
                for c in infer_capabilities(provider_model_id):
                    caps.add(c, Evidence.STATIC_FALLBACK)
        if m.local:
            caps.add(Capability.LOCAL_EXECUTION, Evidence.PROVIDER_METADATA)
        if m.supports_streaming and kind == "chat":
            caps.add(Capability.STREAMING, Evidence.STATIC_FALLBACK)
        return ProviderModelRoute(
            canonical_model_id=kw.pop("canonical_model_id", "") or provider_model_id,
            provider_model_id=provider_model_id, provider_id=m.id, connection_id=self.connection_id,
            route=self.config.get("route_label") or m.route_label, capabilities=caps,
            privacy=Privacy(self.config["privacy"]) if self.config.get("privacy") else m.privacy,
            local=m.local, display_name=display_name or provider_model_id, kind=kind,
            last_discovered_at=time.time(), **kw)

    def apply_overrides(self, routes: list[ProviderModelRoute]) -> list[ProviderModelRoute]:
        """Advanced, user-labelled capability overrides (custom endpoints)."""
        ov = self.config.get("capability_overrides") or {}
        for r in routes:
            for name, val in ov.items():
                try:
                    cap = Capability(name)
                except ValueError:
                    continue
                if val:
                    r.capabilities.add(cap, Evidence.USER_OVERRIDE)
                else:
                    r.capabilities.items.pop(cap.value, None)
        return routes


class DecisionProvider:
    """Typed fast-decision provider. NOT a chat model; cannot produce prose."""
    manifest: ProviderManifest

    def __init__(self, connection_id: str, config: dict[str, Any], secrets: dict[str, str], transport: Transport):
        self.connection_id = connection_id
        self.config = config
        self.secrets = secrets
        self.transport = transport

    def provider_metadata(self) -> dict:
        return self.manifest.public()

    def health(self) -> HealthReport:
        raise NotImplementedError

    def validate_credentials(self) -> HealthReport:
        return self.health()

    def discover_models(self) -> list[ProviderModelRoute]:
        raise NotImplementedError

    def decide(self, model_id: str, state: dict[str, Any], questions: list[DecisionQuestion],
               timeout: float = 15.0) -> list[DecisionAnswer]:
        raise NotImplementedError


def now_ms() -> float:
    return time.perf_counter() * 1000.0
