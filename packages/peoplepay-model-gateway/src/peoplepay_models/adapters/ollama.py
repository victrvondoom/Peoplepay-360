"""Ollama adapter (native API). Local execution boundary.

NOTE: ``localhost:11434`` means the machine the *backend* runs on. A cloud
PeoplePay backend cannot reach a user's laptop; see docs/models/LOCAL_MODELS.md.
"""
from __future__ import annotations

import json
from typing import Iterator

from ..canonical import (Capability as C, CapabilitySet, Evidence, FilePart, Health, ImagePart, Part,
                         ProviderType, Privacy, StreamEvent, StructuredPart, TextPart, ToolCallPart,
                         ToolResultPart, Usage, ProviderModelRoute)
from ..errors import ErrorCode, GatewayError
from ..transport import classify_http
from .base import AdapterResult, CallSpec, CredentialField, HealthReport, ProviderAdapter, ProviderManifest, now_ms

DEFAULT_URL = "http://127.0.0.1:11434"
MAX_SHOW = 60   # bound per-model metadata lookups during discovery


def to_ollama_messages(spec: CallSpec) -> list[dict]:
    out: list[dict] = []
    if spec.system:
        out.append({"role": "system", "content": spec.system})
    for m in spec.messages:
        texts, images, calls, results = [], [], [], []
        for p in m.parts:
            if isinstance(p, TextPart):
                texts.append(p.text)
            elif isinstance(p, StructuredPart):
                texts.append(json.dumps(p.data))
            elif isinstance(p, ImagePart):
                if not p.data_b64:
                    raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, "Ollama needs inline image data, not a URL")
                images.append(p.data_b64)
            elif isinstance(p, FilePart):
                raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, f"file {p.name!r} cannot be sent to Ollama")
            elif isinstance(p, ToolCallPart):
                calls.append({"function": {"name": p.name, "arguments": p.arguments}})
            elif isinstance(p, ToolResultPart):
                results.append(p)
        for r in results:
            out.append({"role": "tool", "content": r.content})
        if m.role == "tool":
            continue
        msg = {"role": m.role, "content": "".join(texts)}
        if images:
            msg["images"] = images
        if calls:
            msg["tool_calls"] = calls
        if msg["content"] or images or calls:
            out.append(msg)
    return out


class OllamaAdapter(ProviderAdapter):
    manifest = ProviderManifest(
        id="ollama", display_name="Ollama", type=ProviderType.LOCAL, protocols=("ollama.chat",),
        discovery_mode="dynamic", route_label="Local (Ollama)", privacy=Privacy.LOCAL, local=True,
        default_base_url=DEFAULT_URL,
        fields=(CredentialField("base_url", "Base URL", default=DEFAULT_URL,
                                help="Must be reachable from the PeoplePay BACKEND, not just your browser."),
                CredentialField("privacy", "Data boundary", required=False, default="local",
                                options=["local", "organization"],
                                help="Use 'organization' only for a remote Ollama you operate yourself.")),
        notice="Runs on hardware you control; no cloud API quota applies, but inference uses local compute.",
        capabilities_hint=(C.TEXT, C.VISION, C.TOOLS, C.STRUCTURED_OUTPUT, C.STREAMING, C.REASONING, C.LOCAL_EXECUTION))

    @property
    def base(self) -> str:
        return (self.config.get("base_url") or DEFAULT_URL).rstrip("/")

    def _call(self, method, path, body=None, *, timeout=30.0, stream=False):
        h = {"Content-Type": "application/json"}
        if self.secrets.get("api_key"):
            h["Authorization"] = f"Bearer {self.secrets['api_key']}"
        resp = self.transport.request(method, self.base + path, headers=h,
                                      body=json.dumps(body).encode() if body is not None else None,
                                      timeout=timeout, stream=stream)
        if not 200 <= resp.status < 300:
            err = classify_http(resp.status, resp.body, resp.headers, local=True)
            if err.code == ErrorCode.PROVIDER_UNAVAILABLE:
                err = GatewayError(ErrorCode.LOCAL_PROVIDER_OFFLINE, err.detail, http_status=resp.status)
            raise err
        return resp

    def _as_local(self, e: GatewayError) -> GatewayError:
        if e.code in (ErrorCode.PROVIDER_UNAVAILABLE,):
            return GatewayError(ErrorCode.LOCAL_PROVIDER_OFFLINE, e.detail)
        return e

    def health(self) -> HealthReport:
        t = now_ms()
        try:
            self._call("GET", "/api/tags", timeout=5)
            return HealthReport(Health.HEALTHY, now_ms() - t)
        except GatewayError as e:
            e = self._as_local(e)
            state = Health.AUTH_ERROR if e.code == ErrorCode.INVALID_CREDENTIALS else \
                Health.RATE_LIMITED if e.code == ErrorCode.RATE_LIMITED else Health.UNAVAILABLE
            return HealthReport(state, now_ms() - t, e.code.value)

    def discover_models(self) -> list[ProviderModelRoute]:
        try:
            tags = self._call("GET", "/api/tags", timeout=10).json()
        except GatewayError as e:
            raise self._as_local(e)
        models = tags.get("models") if isinstance(tags, dict) else None
        if not isinstance(models, list):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "unexpected /api/tags shape")
        routes = []
        for i, m in enumerate(models):
            name = m.get("model") or m.get("name")
            if not name:
                continue
            caps, ctx = None, None
            kind = "chat"
            if i < MAX_SHOW:
                try:
                    show = self._call("POST", "/api/show", {"model": name}, timeout=10).json()
                    declared = show.get("capabilities")
                    if isinstance(declared, list):
                        caps = CapabilitySet()
                        ev = Evidence.PROVIDER_METADATA
                        if "completion" in declared:
                            caps.add(C.TEXT, ev); caps.add(C.STREAMING, ev); caps.add(C.STRUCTURED_OUTPUT, ev)
                        else:
                            kind = "embedding" if "embedding" in declared else "other"
                        if "vision" in declared:
                            caps.add(C.VISION, ev)
                        if "tools" in declared:
                            caps.add(C.TOOLS, ev)
                        if "thinking" in declared:
                            caps.add(C.REASONING, ev)
                        caps.add(C.LOCAL_EXECUTION, ev)
                    for k, v in (show.get("model_info") or {}).items():
                        if k.endswith(".context_length") and isinstance(v, int):
                            ctx = v
                except GatewayError:
                    pass   # fall back to tagged heuristics for this model
            details = m.get("details") or {}
            routes.append(self.route(name, display_name=name, caps=caps, kind=kind if caps else None,
                                     context_window=ctx, model_family=details.get("family")))
        return routes

    def _body(self, spec: CallSpec, stream: bool):
        notes: list[str] = []
        body = {"model": spec.provider_model_id, "messages": to_ollama_messages(spec), "stream": stream}
        opts = {}
        if spec.temperature is not None:
            opts["temperature"] = spec.temperature
        if spec.max_output_tokens:
            opts["num_predict"] = spec.max_output_tokens
        o = spec.provider_options.get("ollama")
        if isinstance(o, dict):
            opts.update(o.get("options", {}))
        if opts:
            body["options"] = opts
        if spec.tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                              "parameters": t.parameters}} for t in spec.tools]
        if spec.response_schema is not None:
            body["format"] = spec.response_schema
        if spec.reasoning.value != "AUTO":
            notes.append(f"reasoning preference {spec.reasoning.value} not mapped for this route; ignored")
        return body, notes

    def normalize_usage(self, raw):
        raw = raw or {}
        return Usage(raw.get("prompt_eval_count"), raw.get("eval_count"), None, None)  # local: no cloud cost

    @staticmethod
    def _calls(msg: dict) -> list[ToolCallPart]:
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            fn = c.get("function") or {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed tool arguments") from None
            if not fn.get("name") or not isinstance(args, dict):
                raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed tool call")
            calls.append(ToolCallPart(f"call_{i}", fn["name"], args))
        return calls

    def generate(self, spec: CallSpec) -> AdapterResult:
        body, notes = self._body(spec, False)
        try:
            data = self._call("POST", "/api/chat", body, timeout=spec.timeout).json()
        except GatewayError as e:
            raise self._as_local(e)
        msg = data.get("message") if isinstance(data, dict) else None
        if not isinstance(msg, dict):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "no message in response")
        parts: list[Part] = []
        if msg.get("content"):
            parts.append(TextPart(msg["content"]))
        parts += self._calls(msg)
        return AdapterResult(parts, self.normalize_usage(data), data.get("done_reason"), data.get("model"), notes=notes)

    def stream(self, spec: CallSpec) -> Iterator[StreamEvent]:
        body, notes = self._body(spec, True)
        try:
            resp = self._call("POST", "/api/chat", body, timeout=spec.timeout, stream=True)
        except GatewayError as e:
            raise self._as_local(e)
        yield StreamEvent("response.started", {"model": spec.provider_model_id})
        last: dict = {}
        for raw in resp.lines or []:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except ValueError:
                raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed stream chunk") from None
            if chunk.get("error"):
                raise GatewayError(ErrorCode.SERVER_ERROR, str(chunk["error"])[:300])
            msg = chunk.get("message") or {}
            if msg.get("content"):
                yield StreamEvent("text.delta", {"text": msg["content"]})
            for c in self._calls(msg):
                yield StreamEvent("tool.started", {"name": c.name, "call_id": c.call_id})
                yield StreamEvent("tool.completed", {"call_id": c.call_id, "name": c.name, "arguments": c.arguments})
            if chunk.get("done"):
                last = chunk
        u = self.normalize_usage(last)
        yield StreamEvent("usage", {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "cached_tokens": None, "cost": None})
        yield StreamEvent("response.completed", {"finish_reason": last.get("done_reason"), "model_used": last.get("model"), "notes": notes})
