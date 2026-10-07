"""Deterministic mock provider: CI, demos and UI walkthroughs without paid APIs.

Behaviour is scriptable per connection via config:
  models: [{id, name, vision, tools, reasoning, context}]
  script: {"fail": ["RATE_LIMITED", ...]}   # consumed one per call, then success
  local:  true => reported as a local route
Responses are formulaic ("[mock:<model>] ...") so nobody mistakes them for AI output.
"""
from __future__ import annotations

import json
import time
from typing import Iterator

from ..canonical import (Capability as C, CapabilitySet, Evidence, Health, Privacy, ProviderType, StreamEvent,
                         TextPart, ToolCallPart, Usage, ProviderModelRoute, ImagePart)
from ..errors import ErrorCode, GatewayError
from .base import AdapterResult, CallSpec, CredentialField, HealthReport, ProviderAdapter, ProviderManifest

_STATE: dict[str, dict] = {}   # connection_id -> counters, shared across adapter rebuilds


class MockAdapter(ProviderAdapter):
    manifest = ProviderManifest(
        id="mock", display_name="Mock (deterministic test provider)", type=ProviderType.CUSTOM,
        protocols=("mock",), discovery_mode="dynamic", route_label="Mock", experimental=True,
        fields=(CredentialField("models_json", "Models (JSON)", required=False),),
        notice="Deterministic stand-in for testing. Not an AI model.", verification="mock")

    @property
    def st(self) -> dict:
        return _STATE.setdefault(self.connection_id, {"calls": 0, "fail": list((self.config.get("script") or {}).get("fail", []))})

    @classmethod
    def reset(cls) -> None:
        _STATE.clear()

    def calls(self) -> int:
        return self.st["calls"]

    def _models(self) -> list[dict]:
        return self.config.get("models") or [{"id": "mock-small", "name": "Mock Small"}]

    def health(self) -> HealthReport:
        if self.config.get("offline"):
            return HealthReport(Health.UNAVAILABLE, None, "offline")
        return HealthReport(Health.HEALTHY, 1.0)

    def discover_models(self):
        if self.config.get("offline"):
            raise GatewayError(ErrorCode.LOCAL_PROVIDER_OFFLINE if self.config.get("local") else ErrorCode.PROVIDER_UNAVAILABLE, "offline")
        out = []
        for m in self._models():
            caps = CapabilitySet.of(Evidence.PROVIDER_METADATA, C.TEXT, C.STREAMING)
            for flag, cap in (("vision", C.VISION), ("tools", C.TOOLS), ("reasoning", C.REASONING), ("structured", C.STRUCTURED_OUTPUT)):
                if m.get(flag):
                    caps.add(cap, Evidence.PROVIDER_METADATA)
            if m.get("context", 0) >= 200_000:
                caps.add(C.LONG_CONTEXT, Evidence.PROVIDER_METADATA)
            r = self.route(m["id"], display_name=m.get("name", m["id"]), caps=caps, context_window=m.get("context", 8192),
                           pricing=m.get("pricing"), model_family=m.get("family"))
            if self.config.get("local"):
                r.local, r.privacy, r.route = True, Privacy.LOCAL, self.config.get("route_label") or "Local (mock)"
                r.capabilities.add(C.LOCAL_EXECUTION, Evidence.PROVIDER_METADATA)
            out.append(r)
        return out

    def _maybe_fail(self):
        self.st["calls"] += 1
        if self.config.get("offline"):
            raise GatewayError(ErrorCode.LOCAL_PROVIDER_OFFLINE if self.config.get("local") else ErrorCode.PROVIDER_UNAVAILABLE, "offline")
        if self.st["fail"]:
            code = self.st["fail"].pop(0)
            if code and code != "OK":
                raise GatewayError(ErrorCode(code), "scripted failure", retry_after=self.config.get("retry_after"))

    def _reply(self, spec: CallSpec) -> str:
        last = next((m for m in reversed(spec.messages) if m.role == "user"), None)
        n_img = sum(1 for m in spec.messages for p in m.parts if isinstance(p, ImagePart))
        text = last.text if last else ""
        if spec.response_schema is not None:
            return json.dumps(self.config.get("structured_reply") or {"ok": True})
        return f"[mock:{spec.provider_model_id}] {text[:200]}" + (f" (saw {n_img} image(s))" if n_img else "")

    def generate(self, spec):
        self._maybe_fail()
        if spec.tools and self.config.get("call_tool"):
            t = spec.tools[0]
            return AdapterResult([ToolCallPart("call_1", t.name, self.config.get("tool_args") or {})],
                                 Usage(10, 5), "tool_calls", spec.provider_model_id)
        if self.config.get("bad_tool_call"):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed tool call")
        reply = self._reply(spec)
        return AdapterResult([TextPart(reply)], Usage(max(1, len(str(spec.messages)) // 4), max(1, len(reply) // 4)),
                             "stop", spec.provider_model_id)

    def stream(self, spec) -> Iterator[StreamEvent]:
        self._maybe_fail()
        yield StreamEvent("response.started", {"model": spec.provider_model_id})
        reply = self._reply(spec)
        for w in reply.split(" "):
            yield StreamEvent("text.delta", {"text": w + " "})
        yield StreamEvent("usage", {"input_tokens": 10, "output_tokens": len(reply) // 4, "cached_tokens": None, "cost": None})
        yield StreamEvent("response.completed", {"finish_reason": "stop", "model_used": spec.provider_model_id, "notes": []})
