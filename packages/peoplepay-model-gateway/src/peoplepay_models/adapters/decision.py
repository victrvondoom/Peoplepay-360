"""Typed decision providers (JEV, Laya). NOT chat models; they cannot write prose.

WIRE-PROTOCOL STATUS: PeoplePay's repository contains no specification for JEV or
Laya. The shared transport below therefore implements a *documented, configurable*
typed-question JSON contract (see docs/models/DECISION_MODELS.md) and is verified
against mocks only. Paths and field names are configuration, so adapting to the real
SystemOne-style protocol is a manifest/config change, not a core change. Do not
treat these adapters as LIVE VERIFIED.
"""
from __future__ import annotations

import json
import time
from typing import Any

from ..canonical import (Capability as C, CapabilitySet, DecisionAnswer, DecisionQuestion, Evidence, Health,
                         ProviderModelRoute, ProviderType)
from ..errors import ErrorCode, GatewayError
from ..transport import classify_http
from .base import CredentialField, DecisionProvider, HealthReport, ProviderManifest, now_ms

KINDS = {"BOOLEAN", "CHOICE", "SCORE", "RATING"}
_KIND_CAP = {"BOOLEAN": C.DECISION_BOOLEAN, "CHOICE": C.DECISION_CHOICE, "SCORE": C.DECISION_SCORE, "RATING": C.DECISION_SCORE}


def _validate_answer(q: DecisionQuestion, a: dict) -> DecisionAnswer:
    v = a.get("value")
    if q.kind == "BOOLEAN":
        if not isinstance(v, bool):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, f"answer to {q.id} is not boolean")
    elif q.kind == "CHOICE":
        if v not in q.choices:
            raise GatewayError(ErrorCode.INVALID_RESPONSE, f"answer to {q.id} is not an allowed choice")
    else:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, f"answer to {q.id} is not numeric")
        if q.scale and not (q.scale[0] <= v <= q.scale[1]):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, f"answer to {q.id} is outside the scale")
    conf = a.get("confidence")
    if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1):
        raise GatewayError(ErrorCode.INVALID_RESPONSE, f"confidence for {q.id} is invalid")
    return DecisionAnswer(q.id, q.kind, v, float(conf) if conf is not None else None)


class SystemOneStyleProvider(DecisionProvider):
    """Shared transport/schema for SystemOne-style typed decision services."""
    manifest: ProviderManifest
    default_paths = {"models": "/models", "decide": "/decide", "health": "/health"}

    @property
    def base(self) -> str:
        b = self.config.get("base_url")
        if not b:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "base_url is required")
        return b.rstrip("/")

    def _path(self, name: str) -> str:
        return (self.config.get("paths") or {}).get(name) or self.default_paths[name]

    def _call(self, method, name, body=None, timeout=15.0):
        h = {"Content-Type": "application/json"}
        if self.secrets.get("api_key"):
            h["Authorization"] = f"Bearer {self.secrets['api_key']}"
        resp = self.transport.request(method, self.base + self._path(name), headers=h,
                                      body=json.dumps(body).encode() if body is not None else None, timeout=timeout)
        if not 200 <= resp.status < 300:
            raise classify_http(resp.status, resp.body, resp.headers)
        return resp.json()

    def health(self) -> HealthReport:
        t = now_ms()
        try:
            self._call("GET", "health", timeout=8)
            return HealthReport(Health.HEALTHY, now_ms() - t)
        except GatewayError as e:
            state = {ErrorCode.INVALID_CREDENTIALS: Health.AUTH_ERROR, ErrorCode.RATE_LIMITED: Health.RATE_LIMITED}.get(e.code, Health.UNAVAILABLE)
            return HealthReport(state, now_ms() - t, e.code.value)

    def discover_models(self) -> list[ProviderModelRoute]:
        data = self._call("GET", "models", timeout=15)
        entries = data.get("models") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "unexpected model list")
        routes = []
        for e in entries:
            e = e if isinstance(e, dict) else {"id": e}
            mid = e.get("id")
            if not mid:
                continue
            caps = CapabilitySet()
            declared = e.get("question_types") or e.get("supports")
            kinds = {str(k).upper() for k in declared} & KINDS if isinstance(declared, list) else set()
            for k in kinds:
                caps.add(_KIND_CAP[k], Evidence.PROVIDER_METADATA)
            routes.append(ProviderModelRoute(
                canonical_model_id=mid, provider_model_id=mid, provider_id=self.manifest.id,
                connection_id=self.connection_id, route=self.manifest.route_label, capabilities=caps,
                privacy=self.manifest.privacy, display_name=e.get("name") or mid, kind="decision",
                last_discovered_at=time.time()))
        return routes

    def decide(self, model_id, state, questions, timeout=15.0):
        if not questions:
            return []
        for q in questions:
            if q.kind not in KINDS:
                raise GatewayError(ErrorCode.INVALID_REQUEST, f"unknown question kind {q.kind!r}")
            if q.kind == "CHOICE" and not q.choices:
                raise GatewayError(ErrorCode.INVALID_REQUEST, f"{q.id}: CHOICE needs choices")
        body = {"model": model_id, "state": state,
                "questions": [{"id": q.id, "type": q.kind, "prompt": q.prompt,
                               **({"choices": q.choices} if q.choices else {}),
                               **({"scale": list(q.scale)} if q.scale else {})} for q in questions]}
        data = self._call("POST", "decide", body, timeout=timeout)
        answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(answers, list):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "no answers in response")
        by_id = {a.get("id"): a for a in answers if isinstance(a, dict)}
        out = []
        for q in questions:
            if q.id not in by_id:
                raise GatewayError(ErrorCode.INVALID_RESPONSE, f"no answer for {q.id}")
            out.append(_validate_answer(q, by_id[q.id]))
        return out


class JevProvider(SystemOneStyleProvider):
    manifest = ProviderManifest(
        id="jev", display_name="JEV", type=ProviderType.DECISION, protocols=("systemone.typed-decision",),
        discovery_mode="dynamic", route_label="JEV decision", kind="decision", supports_streaming=False,
        fields=(CredentialField("base_url", "Base URL"), CredentialField("api_key", "API key", secret=True)),
        notice="Typed fast-decision model. Returns BOOLEAN/CHOICE/SCORE answers, not prose.",
        capabilities_hint=(C.DECISION_BOOLEAN, C.DECISION_CHOICE, C.DECISION_SCORE), verification="mock")


class LayaProvider(SystemOneStyleProvider):
    manifest = ProviderManifest(
        id="laya", display_name="Laya", type=ProviderType.DECISION, protocols=("systemone.typed-decision",),
        discovery_mode="dynamic", route_label="Laya decision", kind="decision", supports_streaming=False,
        fields=(CredentialField("base_url", "Base URL"),
                CredentialField("api_key", "API key", secret=True, required=False,
                                help="Optional, depending on deployment.")),
        notice="Typed fast-decision model. Returns BOOLEAN/CHOICE/SCORE answers, not prose.",
        capabilities_hint=(C.DECISION_BOOLEAN, C.DECISION_CHOICE, C.DECISION_SCORE), verification="mock")
