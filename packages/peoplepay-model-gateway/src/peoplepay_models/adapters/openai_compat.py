"""OpenAI-compatible chat-completions adapter and its flavours.

One transport implementation serves OpenAI, NVIDIA NIM, OpenRouter and arbitrary
compatible endpoints (vLLM, LM Studio, org gateways). Flavours differ only in
manifest, discovery metadata parsing and a few request knobs. Compatible servers do
not all support every OpenAI feature, so capabilities come from provider metadata,
heuristics (tagged weaker) or an explicit capability test -- never assumption.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterator

from ..canonical import (Capability as C, CapabilitySet, Evidence, FilePart, Health, ImagePart,
                         Message, Part, ProviderType, Privacy, Reasoning, StreamEvent, StructuredPart,
                         TextPart, ToolCallPart, ToolResultPart, Usage, ProviderModelRoute)
from ..errors import ErrorCode, GatewayError
from ..transport import classify_http
from .base import (AdapterResult, CallSpec, CredentialField, HealthReport, ProviderAdapter,
                   ProviderManifest, now_ms)

_FORBIDDEN_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "upgrade", "te",
                      "proxy-authorization", "cookie"}


def safe_custom_headers(headers: dict | None, *, has_api_key: bool) -> dict[str, str]:
    """Custom headers are untrusted input: no smuggling, no hop-by-hop, no auth override."""
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        k, v = str(k).strip(), str(v)
        low = k.lower()
        if not k or any(c in k + v for c in "\r\n\0") or len(out) >= 10 or len(v) > 1024:
            continue
        if low in _FORBIDDEN_HEADERS or (low == "authorization" and has_api_key):
            continue
        out[k] = v
    return out


def to_openai_messages(spec: CallSpec) -> list[dict]:
    out: list[dict] = []
    if spec.system:
        out.append({"role": "system", "content": spec.system})
    for m in spec.messages:
        if m.role == "system":
            out.append({"role": "system", "content": m.text})
            continue
        texts, content, calls, results = [], [], [], []
        for p in m.parts:
            if isinstance(p, TextPart):
                texts.append(p.text); content.append({"type": "text", "text": p.text})
            elif isinstance(p, StructuredPart):
                t = json.dumps(p.data); texts.append(t); content.append({"type": "text", "text": t})
            elif isinstance(p, ImagePart):
                url = p.url or f"data:{p.media_type};base64,{p.data_b64}"
                content.append({"type": "image_url", "image_url": {"url": url}})
            elif isinstance(p, FilePart):
                raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY,
                                   f"file attachment {p.name!r} cannot be sent inline to this provider")
            elif isinstance(p, ToolCallPart):
                calls.append({"id": p.call_id, "type": "function",
                              "function": {"name": p.name, "arguments": json.dumps(p.arguments)}})
            elif isinstance(p, ToolResultPart):
                results.append(p)
        if m.role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": "".join(texts) or None}
            if calls:
                msg["tool_calls"] = calls
            if msg["content"] is not None or calls:
                out.append(msg)
        elif m.role in ("user", "tool"):
            for r in results:
                out.append({"role": "tool", "tool_call_id": r.call_id, "content": r.content})
            if content:
                only_text = all(c["type"] == "text" for c in content)
                out.append({"role": "user", "content": "".join(texts) if only_text else content})
    return out


def parse_tool_calls(raw_calls: list[dict] | None) -> list[ToolCallPart]:
    calls = []
    for c in raw_calls or []:
        fn = (c or {}).get("function") or {}
        name, args = fn.get("name"), fn.get("arguments", "{}")
        if not name or not isinstance(name, str):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "tool call without a name")
        try:
            parsed = json.loads(args) if isinstance(args, str) else args
        except ValueError:
            raise GatewayError(ErrorCode.INVALID_RESPONSE, f"malformed arguments for tool {name!r}") from None
        if not isinstance(parsed, dict):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, f"tool {name!r} arguments are not an object")
        calls.append(ToolCallPart(call_id=str(c.get("id") or f"call_{len(calls)}"), name=name, arguments=parsed))
    return calls


class OpenAICompatibleAdapter(ProviderAdapter):
    manifest = ProviderManifest(
        id="openai_compatible", display_name="OpenAI-compatible endpoint", type=ProviderType.CUSTOM,
        protocols=("openai.chat_completions",), discovery_mode="hybrid", route_label="Custom endpoint",
        fields=(
            CredentialField("base_url", "Base URL", required=True, help="e.g. http://host:8000/v1"),
            CredentialField("api_key", "API key", secret=True, required=False),
            CredentialField("models_endpoint", "Models endpoint", required=False, default="/models"),
            CredentialField("manual_models", "Manual model IDs (comma separated)", required=False),
            CredentialField("privacy", "Data boundary", required=False, default="cloud",
                            options=["local", "organization", "cloud"],
                            help="Where this endpoint sends data. Advanced: affects privacy routing."),
        ),
        notice="Custom endpoints are untrusted external systems. Requests sent to them are processed "
               "according to whoever operates them.",
        capabilities_hint=(C.TEXT, C.STREAMING),
    )
    default_base_url: str | None = None
    max_tokens_param = "max_tokens"
    stream_usage_default = False
    models_path = "/models"

    # -- plumbing ------------------------------------------------------------
    @property
    def base(self) -> str:
        b = self.config.get("base_url") or self.default_base_url or self.manifest.default_base_url
        if not b:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "base_url is required")
        return b.rstrip("/")

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        key = self.secrets.get("api_key")
        if key:
            h["Authorization"] = f"Bearer {key}"
        h.update(safe_custom_headers(self.config.get("headers"), has_api_key=bool(key)))
        return h

    def _call(self, method: str, path: str, body: dict | None = None, *, timeout: float = 30.0,
              stream: bool = False):
        raw = json.dumps(body).encode() if body is not None else None
        resp = self.transport.request(method, self.base + path, headers=self._headers(), body=raw,
                                      timeout=timeout, stream=stream)
        if not 200 <= resp.status < 300:
            err = classify_http(resp.status, resp.body, resp.headers, local=self.manifest.local)
            raise err
        return resp

    # -- health / discovery ---------------------------------------------------
    def health(self) -> HealthReport:
        t = now_ms()
        try:
            self._call("GET", self.config.get("models_endpoint") or self.models_path, timeout=10)
            return HealthReport(Health.HEALTHY, now_ms() - t)
        except GatewayError as e:
            if e.code == ErrorCode.MODEL_NOT_FOUND and self.config.get("manual_models"):
                return HealthReport(Health.HEALTHY, now_ms() - t, "models endpoint absent; manual models in use")
            state = {ErrorCode.INVALID_CREDENTIALS: Health.AUTH_ERROR, ErrorCode.RATE_LIMITED: Health.RATE_LIMITED,
                     ErrorCode.QUOTA_EXHAUSTED: Health.RATE_LIMITED}.get(e.code, Health.UNAVAILABLE)
            return HealthReport(state, now_ms() - t, e.code.value)

    def _entry_to_route(self, entry: dict) -> ProviderModelRoute | None:
        mid = entry.get("id") or entry.get("name")
        if not mid or not isinstance(mid, str):
            return None
        return self.route(mid, display_name=entry.get("display_name") or mid)

    def _manual_routes(self) -> list[ProviderModelRoute]:
        raw = self.config.get("manual_models") or []
        ids = [s.strip() for s in raw.split(",")] if isinstance(raw, str) else list(raw)
        return [self.route(i, source="manual") for i in ids if i]

    def discover_models(self) -> list[ProviderModelRoute]:
        routes: list[ProviderModelRoute] = []
        try:
            data = self._call("GET", self.config.get("models_endpoint") or self.models_path, timeout=20).json()
            entries = data.get("data", []) if isinstance(data, dict) else data
            if not isinstance(entries, list):
                raise GatewayError(ErrorCode.INVALID_RESPONSE, "model list has unexpected shape")
            for e in entries:
                r = self._entry_to_route(e if isinstance(e, dict) else {"id": e})
                if r:
                    routes.append(r)
        except GatewayError as e:
            if not self.config.get("manual_models") or e.code in (ErrorCode.INVALID_CREDENTIALS, ErrorCode.RATE_LIMITED):
                raise
        seen = {r.provider_model_id for r in routes}
        routes += [r for r in self._manual_routes() if r.provider_model_id not in seen]
        return self.apply_overrides(routes)

    # -- generation ------------------------------------------------------------
    def _body(self, spec: CallSpec, stream: bool) -> tuple[dict, list[str]]:
        notes: list[str] = []
        body: dict[str, Any] = {"model": spec.provider_model_id, "messages": to_openai_messages(spec)}
        reasoning_model = spec.caps.has(C.REASONING)
        if spec.temperature is not None:
            if reasoning_model and self.manifest.id == "openai":
                notes.append("temperature ignored for reasoning model")
            else:
                body["temperature"] = spec.temperature
        if spec.max_output_tokens:
            body[self.config.get("max_tokens_param") or self.max_tokens_param] = spec.max_output_tokens
        if spec.tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                              "parameters": t.parameters}} for t in spec.tools]
        if spec.response_schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "response", "schema": spec.response_schema}}
        if spec.reasoning != Reasoning.AUTO:
            if reasoning_model and self.manifest.id in ("openai",):
                body["reasoning_effort"] = {Reasoning.FAST: "low", Reasoning.STANDARD: "medium", Reasoning.DEEP: "high"}[spec.reasoning]
            else:
                notes.append(f"reasoning preference {spec.reasoning.value} not mapped for this route; ignored")
        if stream:
            body["stream"] = True
            if self.config.get("stream_usage", self.stream_usage_default):
                body["stream_options"] = {"include_usage": True}
        body.update(spec.provider_options.get(self.manifest.id, {}) if isinstance(spec.provider_options.get(self.manifest.id), dict) else {})
        return body, notes

    def normalize_usage(self, raw):
        raw = raw or {}
        det = raw.get("prompt_tokens_details") or {}
        cost = raw.get("cost")
        return Usage(raw.get("prompt_tokens"), raw.get("completion_tokens"), det.get("cached_tokens"),
                     float(cost) if isinstance(cost, (int, float)) else None)

    def generate(self, spec: CallSpec) -> AdapterResult:
        body, notes = self._body(spec, False)
        data = self._call("POST", "/chat/completions", body, timeout=spec.timeout).json()
        try:
            choice = data["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError, TypeError):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "no choices in response") from None
        parts: list[Part] = []
        if msg.get("content"):
            parts.append(TextPart(msg["content"]) if isinstance(msg["content"], str) else TextPart(json.dumps(msg["content"])))
        parts += parse_tool_calls(msg.get("tool_calls"))
        return AdapterResult(parts, self.normalize_usage(data.get("usage")), choice.get("finish_reason"),
                             data.get("model"), self._served_via(data), notes)

    def _served_via(self, data: dict) -> str | None:
        return None

    def stream(self, spec: CallSpec) -> Iterator[StreamEvent]:
        body, notes = self._body(spec, True)
        resp = self._call("POST", "/chat/completions", body, timeout=spec.timeout, stream=True)
        yield StreamEvent("response.started", {"model": spec.provider_model_id})
        tool_acc: dict[int, dict] = {}
        finish, usage, model = None, None, None
        for raw in resp.lines or []:
            line = raw.decode("utf-8", "replace").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except ValueError:
                raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed stream chunk") from None
            if chunk.get("error"):
                raise GatewayError(ErrorCode.SERVER_ERROR, json.dumps(chunk["error"])[:300])
            model = chunk.get("model") or model
            if chunk.get("usage"):
                usage = chunk["usage"]
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content"):
                    yield StreamEvent("text.delta", {"text": d["content"]})
                for tc in d.get("tool_calls") or []:
                    slot = tool_acc.setdefault(tc.get("index", 0), {"id": None, "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        if not slot["name"]:
                            yield StreamEvent("tool.started", {"name": fn["name"], "call_id": slot["id"]})
                        slot["name"] += fn["name"]
                    slot["arguments"] += fn.get("arguments") or ""
                finish = ch.get("finish_reason") or finish
        for _, s in sorted(tool_acc.items()):
            call = parse_tool_calls([{"id": s["id"], "function": {"name": s["name"], "arguments": s["arguments"] or "{}"}}])[0]
            yield StreamEvent("tool.completed", {"call_id": call.call_id, "name": call.name, "arguments": call.arguments})
        u = self.normalize_usage(usage)
        yield StreamEvent("usage", {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                                    "cached_tokens": u.cached_tokens, "cost": u.estimated_cost})
        yield StreamEvent("response.completed", {"finish_reason": finish, "model_used": model, "notes": notes})

    def normalize_error(self, exc):
        return exc if isinstance(exc, GatewayError) else super().normalize_error(exc)


class OpenAIAdapter(OpenAICompatibleAdapter):
    manifest = ProviderManifest(
        id="openai", display_name="OpenAI", type=ProviderType.DIRECT, protocols=("openai.chat_completions",),
        discovery_mode="dynamic", route_label="Direct (OpenAI)", default_base_url="https://api.openai.com/v1",
        fields=(CredentialField("api_key", "API key", secret=True),
                CredentialField("base_url", "Base URL", required=False, default="https://api.openai.com/v1"),
                CredentialField("organization", "Organization (optional)", required=False),
                CredentialField("project", "Project (optional)", required=False)),
        notice="Requests are processed by OpenAI under your account's terms.",
        capabilities_hint=(C.TEXT, C.VISION, C.TOOLS, C.STRUCTURED_OUTPUT, C.STREAMING, C.REASONING))
    max_tokens_param = "max_completion_tokens"
    stream_usage_default = True

    def _headers(self):
        h = super()._headers()
        if self.config.get("organization"):
            h["OpenAI-Organization"] = str(self.config["organization"])
        if self.config.get("project"):
            h["OpenAI-Project"] = str(self.config["project"])
        return h


class NvidiaNimAdapter(OpenAICompatibleAdapter):
    manifest = ProviderManifest(
        id="nvidia_nim", display_name="NVIDIA NIM", type=ProviderType.DIRECT,
        protocols=("openai.chat_completions",), discovery_mode="dynamic", route_label="NVIDIA NIM",
        default_base_url="https://integrate.api.nvidia.com/v1",
        fields=(CredentialField("api_key", "API key", secret=True, required=False,
                                help="Required for hosted NIM; optional for self-hosted."),
                CredentialField("base_url", "Base URL", required=False, default="https://integrate.api.nvidia.com/v1",
                                help="Point at a self-hosted NIM, e.g. http://nim:8000/v1"),
                CredentialField("privacy", "Data boundary", required=False, default="cloud",
                                options=["local", "organization", "cloud"],
                                help="Set to local/organization for self-hosted NIM.")),
        notice="Hosted NIM requests are processed by NVIDIA under its API terms (trial terms may differ).",
        capabilities_hint=(C.TEXT, C.STREAMING, C.TOOLS, C.VISION))
    stream_usage_default = True

    def health(self) -> HealthReport:
        # Self-hosted NIM exposes a readiness probe; hosted NIM is checked via the catalog.
        if self.base != "https://integrate.api.nvidia.com/v1":
            root = self.base[:-3] if self.base.endswith("/v1") else self.base
            t = now_ms()
            try:
                resp = self.transport.request("GET", root + "/v1/health/ready", headers=self._headers(), timeout=5)
                if resp.status == 200:
                    return HealthReport(Health.HEALTHY, now_ms() - t, "NIM reports ready")
                if resp.status in (401, 403):
                    return HealthReport(Health.AUTH_ERROR, now_ms() - t)
                return HealthReport(Health.DEGRADED, now_ms() - t, f"readiness probe returned {resp.status}")
            except GatewayError:
                pass  # fall through to the catalog check
        return super().health()


class OpenRouterAdapter(OpenAICompatibleAdapter):
    manifest = ProviderManifest(
        id="openrouter", display_name="OpenRouter", type=ProviderType.AGGREGATOR,
        protocols=("openai.chat_completions",), discovery_mode="dynamic", route_label="OpenRouter",
        default_base_url="https://openrouter.ai/api/v1",
        fields=(CredentialField("api_key", "API key", secret=True),
                CredentialField("app_referer", "App URL (HTTP-Referer, optional)", required=False),
                CredentialField("app_title", "App name (X-Title, optional)", required=False)),
        notice="OpenRouter forwards requests to the upstream provider it selects; both OpenRouter's and "
               "the upstream provider's terms apply.",
        capabilities_hint=(C.TEXT, C.VISION, C.TOOLS, C.STRUCTURED_OUTPUT, C.REASONING, C.STREAMING))
    stream_usage_default = True

    def _headers(self):
        h = super()._headers()
        if self.config.get("app_referer"):
            h["HTTP-Referer"] = str(self.config["app_referer"])
        if self.config.get("app_title"):
            h["X-Title"] = str(self.config["app_title"])
        return h

    def _entry_to_route(self, e):
        mid = e.get("id")
        if not mid:
            return None
        arch = e.get("architecture") or {}
        inputs = set(arch.get("input_modalities") or [])
        outputs = set(arch.get("output_modalities") or [])
        params = set(e.get("supported_parameters") or [])
        caps = CapabilitySet()
        ev = Evidence.PROVIDER_METADATA
        if not outputs or "text" in outputs:
            caps.add(C.TEXT, ev)
            caps.add(C.STREAMING, ev)
        if "image" in inputs:
            caps.add(C.VISION, ev)
        if "file" in inputs:
            caps.add(C.FILES, ev)
        if "audio" in inputs:
            caps.add(C.AUDIO_INPUT, ev)
        if "image" in outputs:
            caps.add(C.IMAGE_GENERATION, ev)
        if "tools" in params:
            caps.add(C.TOOLS, ev)
        if params & {"structured_outputs", "response_format"}:
            caps.add(C.STRUCTURED_OUTPUT, ev)
        if params & {"reasoning", "include_reasoning"}:
            caps.add(C.REASONING, ev)
        ctx = e.get("context_length")
        if isinstance(ctx, int) and ctx >= 200_000:
            caps.add(C.LONG_CONTEXT, ev)
        pricing = None
        pr = e.get("pricing") or {}
        try:
            # OpenRouter quotes USD per token as strings; store per 1M tokens.
            pricing = {"input_per_mtok": float(pr["prompt"]) * 1e6, "output_per_mtok": float(pr["completion"]) * 1e6}
        except (KeyError, TypeError, ValueError):
            pricing = None
        kind = "chat" if caps.has(C.TEXT) else "other"
        top = e.get("top_provider") or {}
        return self.route(mid, display_name=e.get("name") or mid, caps=caps, pricing=pricing, kind=kind,
                          context_window=ctx if isinstance(ctx, int) else None,
                          max_output=top.get("max_completion_tokens") if isinstance(top.get("max_completion_tokens"), int) else None)

    def _served_via(self, data):
        p = data.get("provider")
        return p if isinstance(p, str) else None


class CustomOpenAIAdapter(OpenAICompatibleAdapter):
    pass  # manifest inherited: id "openai_compatible"
