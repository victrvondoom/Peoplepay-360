"""Anthropic Messages API adapter (direct)."""
from __future__ import annotations

import json
from typing import Iterator

from ..canonical import (Capability as C, CapabilitySet, Evidence, FilePart, Health, ImagePart, Part,
                         ProviderType, StreamEvent, StructuredPart, TextPart, ToolCallPart, ToolResultPart,
                         Usage, ProviderModelRoute)
from ..errors import ErrorCode, GatewayError
from ..transport import classify_http
from .base import AdapterResult, CallSpec, CredentialField, HealthReport, ProviderAdapter, ProviderManifest, now_ms

API_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096   # the API requires max_tokens; documented default when the caller sets none


def to_anthropic_messages(spec: CallSpec) -> list[dict]:
    out: list[dict] = []
    for m in spec.messages:
        if m.role == "system":
            continue  # carried in the top-level system field by the caller
        blocks: list[dict] = []
        for p in m.parts:
            if isinstance(p, TextPart):
                if p.text:
                    blocks.append({"type": "text", "text": p.text})
            elif isinstance(p, StructuredPart):
                blocks.append({"type": "text", "text": json.dumps(p.data)})
            elif isinstance(p, ImagePart):
                if p.data_b64:
                    blocks.append({"type": "image", "source": {"type": "base64", "media_type": p.media_type, "data": p.data_b64}})
                elif p.url:
                    blocks.append({"type": "image", "source": {"type": "url", "url": p.url}})
            elif isinstance(p, FilePart):
                if p.media_type == "application/pdf" and p.data_b64:
                    blocks.append({"type": "document", "source": {"type": "base64", "media_type": p.media_type, "data": p.data_b64}})
                else:
                    raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, f"file {p.name!r} ({p.media_type}) cannot be sent inline")
            elif isinstance(p, ToolCallPart):
                blocks.append({"type": "tool_use", "id": p.call_id, "name": p.name, "input": p.arguments})
            elif isinstance(p, ToolResultPart):
                blocks.append({"type": "tool_result", "tool_use_id": p.call_id, "content": p.content, "is_error": p.is_error})
        if not blocks:
            continue
        role = "assistant" if m.role == "assistant" else "user"
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)    # API requires alternating roles
        else:
            out.append({"role": role, "content": blocks})
    return out


class AnthropicAdapter(ProviderAdapter):
    manifest = ProviderManifest(
        id="anthropic", display_name="Anthropic", type=ProviderType.DIRECT, protocols=("anthropic.messages",),
        discovery_mode="dynamic", route_label="Direct (Anthropic)", default_base_url="https://api.anthropic.com",
        fields=(CredentialField("api_key", "API key", secret=True),
                CredentialField("base_url", "Base URL", required=False, default="https://api.anthropic.com"),
                CredentialField("anthropic_version", "API version header", required=False, default=API_VERSION)),
        notice="Requests are processed by Anthropic under your account's terms.",
        capabilities_hint=(C.TEXT, C.VISION, C.TOOLS, C.STRUCTURED_OUTPUT, C.STREAMING, C.REASONING, C.FILES))

    @property
    def base(self) -> str:
        return (self.config.get("base_url") or self.manifest.default_base_url).rstrip("/")

    def _headers(self) -> dict[str, str]:
        h = {"content-type": "application/json", "anthropic-version": self.config.get("anthropic_version") or API_VERSION}
        if self.secrets.get("api_key"):
            h["x-api-key"] = self.secrets["api_key"]
        return h

    def _call(self, method, path, body=None, *, timeout=30.0, stream=False):
        resp = self.transport.request(method, self.base + path, headers=self._headers(),
                                      body=json.dumps(body).encode() if body is not None else None,
                                      timeout=timeout, stream=stream)
        if not 200 <= resp.status < 300:
            raise classify_http(resp.status, resp.body, resp.headers)
        return resp

    def health(self) -> HealthReport:
        t = now_ms()
        try:
            self._call("GET", "/v1/models?limit=1", timeout=10)
            return HealthReport(Health.HEALTHY, now_ms() - t)
        except GatewayError as e:
            state = {ErrorCode.INVALID_CREDENTIALS: Health.AUTH_ERROR, ErrorCode.RATE_LIMITED: Health.RATE_LIMITED,
                     ErrorCode.QUOTA_EXHAUSTED: Health.RATE_LIMITED}.get(e.code, Health.UNAVAILABLE)
            return HealthReport(state, now_ms() - t, e.code.value)

    def discover_models(self) -> list[ProviderModelRoute]:
        routes, after = [], None
        for _ in range(20):  # bounded pagination
            path = "/v1/models?limit=100" + (f"&after_id={after}" if after else "")
            data = self._call("GET", path, timeout=20).json()
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise GatewayError(ErrorCode.INVALID_RESPONSE, "model list has unexpected shape")
            for e in data["data"]:
                mid = e.get("id")
                if not mid:
                    continue
                caps = CapabilitySet()
                meta = e.get("capabilities")
                if isinstance(meta, dict):      # newer catalogs describe capabilities: trust them
                    caps.add(C.TEXT, Evidence.PROVIDER_METADATA)
                    if (meta.get("image_input") or {}).get("supported"):
                        caps.add(C.VISION, Evidence.PROVIDER_METADATA)
                    if (meta.get("structured_outputs") or {}).get("supported"):
                        caps.add(C.STRUCTURED_OUTPUT, Evidence.PROVIDER_METADATA)
                    if (meta.get("thinking") or {}).get("supported"):
                        caps.add(C.REASONING, Evidence.PROVIDER_METADATA)
                    if (meta.get("pdf_input") or {}).get("supported"):
                        caps.add(C.FILES, Evidence.PROVIDER_METADATA)
                    caps.add(C.TOOLS, Evidence.STATIC_FALLBACK)  # tool use is not in the catalog
                    caps.add(C.STREAMING, Evidence.STATIC_FALLBACK)
                else:
                    caps = None   # route() applies tagged heuristics
                ctx = e.get("max_input_tokens")
                r = self.route(mid, display_name=e.get("display_name") or mid, caps=caps,
                               context_window=ctx if isinstance(ctx, int) else None,
                               max_output=e.get("max_tokens") if isinstance(e.get("max_tokens"), int) else None,
                               kind="chat")
                if isinstance(ctx, int) and ctx >= 200_000:
                    r.capabilities.add(C.LONG_CONTEXT, Evidence.PROVIDER_METADATA)
                routes.append(r)
            if not data.get("has_more"):
                break
            after = data.get("last_id")
            if not after:
                break
        return routes

    def _body(self, spec: CallSpec, stream: bool):
        notes: list[str] = []
        system = spec.system
        extra_sys = [m.text for m in spec.messages if m.role == "system"]
        if extra_sys:
            system = "\n\n".join(filter(None, [system, *extra_sys]))
        body = {"model": spec.provider_model_id, "messages": to_anthropic_messages(spec),
                "max_tokens": spec.max_output_tokens or DEFAULT_MAX_TOKENS}
        if system:
            body["system"] = system
        if spec.temperature is not None:
            body["temperature"] = spec.temperature
        if spec.tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in spec.tools]
        if spec.response_schema is not None:
            # No portable native flag: instruct, then the gateway validates. Declared, not hidden.
            import json as _j
            body["system"] = ((body.get("system") or "") + "\n\nRespond with ONLY a JSON value matching this JSON Schema:\n" + _j.dumps(spec.response_schema)).strip()
            notes.append("structured output via instruction + gateway validation")
        if spec.reasoning.value not in ("AUTO",):
            notes.append(f"reasoning preference {spec.reasoning.value} not mapped for this route; use provider_options.anthropic.thinking to set it explicitly")
        opts = spec.provider_options.get("anthropic")
        if isinstance(opts, dict):
            body.update(opts)
        if stream:
            body["stream"] = True
        return body, notes

    def normalize_usage(self, raw):
        raw = raw or {}
        return Usage(raw.get("input_tokens"), raw.get("output_tokens"), raw.get("cache_read_input_tokens"))

    def generate(self, spec: CallSpec) -> AdapterResult:
        body, notes = self._body(spec, False)
        data = self._call("POST", "/v1/messages", body, timeout=spec.timeout).json()
        if not isinstance(data, dict) or not isinstance(data.get("content"), list):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "no content in response")
        parts: list[Part] = []
        for b in data["content"]:
            if b.get("type") == "text":
                parts.append(TextPart(b.get("text", "")))
            elif b.get("type") == "tool_use":
                if not isinstance(b.get("input"), dict) or not b.get("name"):
                    raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed tool_use block")
                parts.append(ToolCallPart(str(b.get("id")), b["name"], b["input"]))
        return AdapterResult(parts, self.normalize_usage(data.get("usage")), data.get("stop_reason"), data.get("model"), notes=notes)

    def stream(self, spec: CallSpec) -> Iterator[StreamEvent]:
        body, notes = self._body(spec, True)
        resp = self._call("POST", "/v1/messages", body, timeout=spec.timeout, stream=True)
        yield StreamEvent("response.started", {"model": spec.provider_model_id})
        blocks: dict[int, dict] = {}
        usage: dict = {}
        finish, model = None, None
        for raw in resp.lines or []:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed stream chunk") from None
            t = ev.get("type")
            if t == "message_start":
                msg = ev.get("message") or {}
                model = msg.get("model")
                usage.update(msg.get("usage") or {})
            elif t == "content_block_start":
                cb = ev.get("content_block") or {}
                blocks[ev.get("index", 0)] = {"type": cb.get("type"), "id": cb.get("id"), "name": cb.get("name"), "json": ""}
                if cb.get("type") == "tool_use":
                    yield StreamEvent("tool.started", {"name": cb.get("name"), "call_id": cb.get("id")})
            elif t == "content_block_delta":
                d = ev.get("delta") or {}
                if d.get("type") == "text_delta":
                    yield StreamEvent("text.delta", {"text": d.get("text", "")})
                elif d.get("type") == "input_json_delta":
                    blocks.setdefault(ev.get("index", 0), {"json": ""})["json"] += d.get("partial_json", "")
            elif t == "content_block_stop":
                b = blocks.get(ev.get("index", 0))
                if b and b.get("type") == "tool_use":
                    try:
                        args = json.loads(b["json"] or "{}")
                    except ValueError:
                        raise GatewayError(ErrorCode.INVALID_RESPONSE, f"malformed arguments for tool {b.get('name')!r}") from None
                    if not isinstance(args, dict):
                        raise GatewayError(ErrorCode.INVALID_RESPONSE, "tool arguments are not an object")
                    yield StreamEvent("tool.completed", {"call_id": b["id"], "name": b["name"], "arguments": args})
            elif t == "message_delta":
                finish = (ev.get("delta") or {}).get("stop_reason") or finish
                usage.update(ev.get("usage") or {})
            elif t == "error":
                err = ev.get("error") or {}
                code = ErrorCode.RATE_LIMITED if err.get("type") == "rate_limit_error" else \
                    ErrorCode.PROVIDER_UNAVAILABLE if err.get("type") == "overloaded_error" else ErrorCode.SERVER_ERROR
                raise GatewayError(code, str(err.get("message", ""))[:300])
        u = self.normalize_usage(usage)
        yield StreamEvent("usage", {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                                    "cached_tokens": u.cached_tokens, "cost": None})
        yield StreamEvent("response.completed", {"finish_reason": finish, "model_used": model, "notes": notes})
