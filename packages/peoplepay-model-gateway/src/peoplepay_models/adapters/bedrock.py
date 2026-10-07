"""Amazon Bedrock adapter (Converse API; boto3 or an injected client).

Uses the common Converse/ConverseStream interface so model schemas need not be known.
Model discovery: ListFoundationModels (+ inference profiles). Bedrock's catalog does
NOT say whether the account has been granted access to a model; that surfaces at
invoke time as AccessDenied -> MODEL_UNAVAILABLE, and is never presumed here.
"""
from __future__ import annotations

import base64
import json
from typing import Any, Callable, Iterator

from ..canonical import (Capability as C, CapabilitySet, Evidence, FilePart, Health, ImagePart, Part,
                         ProviderType, StreamEvent, StructuredPart, TextPart, ToolCallPart, ToolResultPart,
                         Usage, ProviderModelRoute, Privacy)
from ..errors import ErrorCode, GatewayError, redact
from .base import AdapterResult, CallSpec, CredentialField, HealthReport, ProviderAdapter, ProviderManifest, now_ms

ClientFactory = Callable[[str, dict, dict], Any]   # (service, config, secrets) -> client


def default_client_factory(service: str, config: dict, secrets: dict):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, "boto3 is not installed; install peoplepay-model-gateway[bedrock]") from exc
    strategy = config.get("credential_strategy", "default_chain")
    kw: dict[str, Any] = {"region_name": config.get("region") or "us-east-1",
                          "config": Config(retries={"max_attempts": 1}, read_timeout=60, connect_timeout=10)}
    session_kw: dict[str, Any] = {}
    if strategy == "static_keys":
        kw.update(aws_access_key_id=secrets.get("access_key_id"), aws_secret_access_key=secrets.get("secret_access_key"))
        if secrets.get("session_token"):
            kw["aws_session_token"] = secrets["session_token"]
    elif strategy == "profile" and config.get("profile"):
        session_kw["profile_name"] = config["profile"]
    session = boto3.Session(**session_kw)
    if strategy == "assume_role" and config.get("role_arn"):
        sts = session.client("sts", region_name=kw["region_name"])
        c = sts.assume_role(RoleArn=config["role_arn"], RoleSessionName="peoplepay-models")["Credentials"]
        kw.update(aws_access_key_id=c["AccessKeyId"], aws_secret_access_key=c["SecretAccessKey"], aws_session_token=c["SessionToken"])
    return session.client(service, **kw)


_ERR = {
    "ThrottlingException": ErrorCode.RATE_LIMITED, "TooManyRequestsException": ErrorCode.RATE_LIMITED,
    "ServiceQuotaExceededException": ErrorCode.QUOTA_EXHAUSTED,
    "UnrecognizedClientException": ErrorCode.INVALID_CREDENTIALS, "InvalidSignatureException": ErrorCode.INVALID_CREDENTIALS,
    "ExpiredTokenException": ErrorCode.INVALID_CREDENTIALS, "InvalidClientTokenId": ErrorCode.INVALID_CREDENTIALS,
    "AccessDeniedException": ErrorCode.MODEL_UNAVAILABLE,   # model access not granted/enabled in this account/region
    "ResourceNotFoundException": ErrorCode.MODEL_NOT_FOUND,
    "ModelNotReadyException": ErrorCode.MODEL_UNAVAILABLE, "ModelErrorException": ErrorCode.SERVER_ERROR,
    "ModelTimeoutException": ErrorCode.TIMEOUT, "ServiceUnavailableException": ErrorCode.PROVIDER_UNAVAILABLE,
    "InternalServerException": ErrorCode.SERVER_ERROR, "ModelStreamErrorException": ErrorCode.SERVER_ERROR,
}


def map_client_error(exc: Exception) -> GatewayError:
    if isinstance(exc, GatewayError):
        return exc
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        err = resp.get("Error") or {}
        code, msg = err.get("Code", ""), err.get("Message", "")
        if code == "ValidationException" and any(s in msg.lower() for s in ("too long", "too many tokens", "context")):
            return GatewayError(ErrorCode.CONTEXT_TOO_LARGE, msg, provider_code=code)
        if code == "AccessDeniedException" and "not authorized" in msg.lower() and "bedrock:" in msg:
            return GatewayError(ErrorCode.INVALID_CREDENTIALS, "IAM principal lacks Bedrock permissions", provider_code=code)
        return GatewayError(_ERR.get(code, ErrorCode.INVALID_REQUEST if code == "ValidationException" else ErrorCode.PROVIDER_UNAVAILABLE),
                            msg, provider_code=code)
    name = type(exc).__name__
    if "NoCredentials" in name or "PartialCredentials" in name:
        return GatewayError(ErrorCode.INVALID_CREDENTIALS, "no usable AWS credentials")
    if "Timeout" in name:
        return GatewayError(ErrorCode.TIMEOUT, name)
    if "EndpointConnection" in name or "Connect" in name:
        return GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, name)
    return GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, name)


_IMG_FMT = {"image/png": "png", "image/jpeg": "jpeg", "image/jpg": "jpeg", "image/gif": "gif", "image/webp": "webp"}


def to_converse(spec: CallSpec) -> tuple[list[dict], list[dict]]:
    system = [{"text": spec.system}] if spec.system else []
    msgs: list[dict] = []
    for m in spec.messages:
        if m.role == "system":
            system.append({"text": m.text}); continue
        blocks: list[dict] = []
        for p in m.parts:
            if isinstance(p, TextPart):
                if p.text:
                    blocks.append({"text": p.text})
            elif isinstance(p, StructuredPart):
                blocks.append({"text": json.dumps(p.data)})
            elif isinstance(p, ImagePart):
                if not p.data_b64 or p.media_type not in _IMG_FMT:
                    raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, "Bedrock needs inline png/jpeg/gif/webp images")
                blocks.append({"image": {"format": _IMG_FMT[p.media_type], "source": {"bytes": base64.b64decode(p.data_b64)}}})
            elif isinstance(p, FilePart):
                raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, f"file {p.name!r} not supported on this route")
            elif isinstance(p, ToolCallPart):
                blocks.append({"toolUse": {"toolUseId": p.call_id, "name": p.name, "input": p.arguments}})
            elif isinstance(p, ToolResultPart):
                blocks.append({"toolResult": {"toolUseId": p.call_id, "content": [{"text": p.content}],
                                              "status": "error" if p.is_error else "success"}})
        if not blocks:
            continue
        role = "assistant" if m.role == "assistant" else "user"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"].extend(blocks)
        else:
            msgs.append({"role": role, "content": blocks})
    return system, msgs


class BedrockAdapter(ProviderAdapter):
    manifest = ProviderManifest(
        id="bedrock", display_name="Amazon Bedrock", type=ProviderType.ENTERPRISE_PLATFORM,
        protocols=("bedrock.converse",), discovery_mode="dynamic", route_label="Amazon Bedrock",
        fields=(CredentialField("region", "AWS region", default="us-east-1"),
                CredentialField("credential_strategy", "Credential strategy", default="default_chain",
                                options=["default_chain", "static_keys", "profile", "assume_role"],
                                help="default_chain uses the backend's IAM role/env; prefer roles over keys."),
                CredentialField("profile", "Profile name", required=False),
                CredentialField("role_arn", "Role ARN", required=False),
                CredentialField("access_key_id", "Access key ID", secret=True, required=False),
                CredentialField("secret_access_key", "Secret access key", secret=True, required=False),
                CredentialField("session_token", "Session token", secret=True, required=False),
                CredentialField("privacy", "Data boundary", required=False, default="organization",
                                options=["organization", "cloud"])),
        privacy=Privacy.ORGANIZATION,
        notice="Requests are processed inside your AWS account/region under your AWS agreement and the model "
               "provider's Bedrock terms. Model access must be enabled in your account.",
        capabilities_hint=(C.TEXT, C.VISION, C.TOOLS, C.STREAMING))

    def __init__(self, *a, client_factory: ClientFactory | None = None, **kw):
        super().__init__(*a, **kw)
        self._factory = client_factory or default_client_factory
        self._clients: dict[str, Any] = {}

    def _client(self, service: str):
        if service not in self._clients:
            self._clients[service] = self._factory(service, self.config, self.secrets)
        return self._clients[service]

    def health(self) -> HealthReport:
        t = now_ms()
        try:
            self._client("bedrock").list_foundation_models(byOutputModality="TEXT")
            return HealthReport(Health.HEALTHY, now_ms() - t)
        except Exception as exc:
            e = map_client_error(exc)
            state = Health.AUTH_ERROR if e.code == ErrorCode.INVALID_CREDENTIALS else \
                Health.RATE_LIMITED if e.code == ErrorCode.RATE_LIMITED else Health.UNAVAILABLE
            return HealthReport(state, now_ms() - t, e.code.value)

    def discover_models(self) -> list[ProviderModelRoute]:
        try:
            client = self._client("bedrock")
            summaries = client.list_foundation_models(byOutputModality="TEXT").get("modelSummaries", [])
            try:
                profiles = client.list_inference_profiles().get("inferenceProfileSummaries", [])
            except Exception:
                profiles = []   # profile listing is optional; absence must not hide models
        except Exception as exc:
            raise map_client_error(exc)
        by_model: dict[str, list[str]] = {}
        for p in profiles:
            for mm in p.get("models") or []:
                arn = mm.get("modelArn", "")
                by_model.setdefault(arn.rsplit("/", 1)[-1], []).append(p.get("inferenceProfileId"))
        routes = []
        region = self.config.get("region")
        for s in summaries:
            mid = s.get("modelId")
            if not mid:
                continue
            life = (s.get("modelLifecycle") or {}).get("status", "ACTIVE")
            types = s.get("inferenceTypesSupported") or []
            invoke_id, note = mid, None
            if types and "ON_DEMAND" not in types:
                prof = [x for x in by_model.get(mid, []) if x]
                if not prof:
                    continue          # cannot be invoked without a profile we do not know about
                invoke_id, note = prof[0], "via inference profile"
            ins = set(s.get("inputModalities") or [])
            caps = CapabilitySet()
            caps.add(C.TEXT, Evidence.PROVIDER_METADATA)
            if "IMAGE" in ins:
                caps.add(C.VISION, Evidence.PROVIDER_METADATA)
            if s.get("responseStreamingSupported"):
                caps.add(C.STREAMING, Evidence.PROVIDER_METADATA)
            from ..heuristics import infer_capabilities
            if C.TOOLS in infer_capabilities(mid):          # catalog has no tool flag: tagged heuristic
                caps.add(C.TOOLS, Evidence.STATIC_FALLBACK)
            r = self.route(invoke_id, display_name=s.get("modelName") or mid, caps=caps, region=region,
                           model_family=s.get("providerName"), kind="chat",
                           availability="deprecated" if life == "LEGACY" else "available")
            r.status = note or "ok"
            routes.append(r)
        return self.apply_overrides(routes)

    def _kwargs(self, spec: CallSpec):
        system, msgs = to_converse(spec)
        kw: dict[str, Any] = {"modelId": spec.provider_model_id, "messages": msgs}
        if system:
            kw["system"] = system
        inf = {}
        if spec.max_output_tokens:
            inf["maxTokens"] = spec.max_output_tokens
        if spec.temperature is not None:
            inf["temperature"] = spec.temperature
        if inf:
            kw["inferenceConfig"] = inf
        if spec.tools:
            kw["toolConfig"] = {"tools": [{"toolSpec": {"name": t.name, "description": t.description,
                                                         "inputSchema": {"json": t.parameters}}} for t in spec.tools]}
        extra = spec.provider_options.get("bedrock")
        if isinstance(extra, dict) and isinstance(extra.get("additionalModelRequestFields"), dict):
            kw["additionalModelRequestFields"] = extra["additionalModelRequestFields"]
        notes = []
        if spec.response_schema is not None:
            notes.append("structured output via gateway validation")
        if spec.reasoning.value != "AUTO":
            notes.append(f"reasoning preference {spec.reasoning.value} not mapped for this route; ignored")
        return kw, notes

    def normalize_usage(self, raw):
        raw = raw or {}
        return Usage(raw.get("inputTokens"), raw.get("outputTokens"), raw.get("cacheReadInputTokens"))

    def generate(self, spec: CallSpec) -> AdapterResult:
        kw, notes = self._kwargs(spec)
        try:
            data = self._client("bedrock-runtime").converse(**kw)
        except Exception as exc:
            raise map_client_error(exc)
        try:
            content = data["output"]["message"]["content"]
        except (KeyError, TypeError):
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "no message in Converse response") from None
        parts: list[Part] = []
        for b in content:
            if "text" in b:
                parts.append(TextPart(b["text"]))
            elif "toolUse" in b:
                tu = b["toolUse"]
                if not isinstance(tu.get("input"), dict) or not tu.get("name"):
                    raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed toolUse block")
                parts.append(ToolCallPart(str(tu.get("toolUseId")), tu["name"], tu["input"]))
        return AdapterResult(parts, self.normalize_usage(data.get("usage")), data.get("stopReason"),
                             spec.provider_model_id, notes=notes)

    def stream(self, spec: CallSpec) -> Iterator[StreamEvent]:
        kw, notes = self._kwargs(spec)
        try:
            resp = self._client("bedrock-runtime").converse_stream(**kw)
        except Exception as exc:
            raise map_client_error(exc)
        yield StreamEvent("response.started", {"model": spec.provider_model_id})
        tools: dict[int, dict] = {}
        finish, usage = None, {}
        try:
            for ev in resp.get("stream", []):
                if "contentBlockStart" in ev:
                    st = ev["contentBlockStart"].get("start", {}).get("toolUse")
                    if st:
                        tools[ev["contentBlockStart"].get("contentBlockIndex", 0)] = {"id": st.get("toolUseId"), "name": st.get("name"), "json": ""}
                        yield StreamEvent("tool.started", {"name": st.get("name"), "call_id": st.get("toolUseId")})
                elif "contentBlockDelta" in ev:
                    d = ev["contentBlockDelta"]
                    delta = d.get("delta", {})
                    if "text" in delta:
                        yield StreamEvent("text.delta", {"text": delta["text"]})
                    elif "toolUse" in delta:
                        tools.setdefault(d.get("contentBlockIndex", 0), {"id": None, "name": None, "json": ""})["json"] += delta["toolUse"].get("input", "")
                elif "contentBlockStop" in ev:
                    t = tools.get(ev["contentBlockStop"].get("contentBlockIndex", 0))
                    if t:
                        try:
                            args = json.loads(t["json"] or "{}")
                        except ValueError:
                            raise GatewayError(ErrorCode.INVALID_RESPONSE, "malformed tool arguments") from None
                        yield StreamEvent("tool.completed", {"call_id": t["id"], "name": t["name"], "arguments": args})
                elif "messageStop" in ev:
                    finish = ev["messageStop"].get("stopReason")
                elif "metadata" in ev:
                    usage = ev["metadata"].get("usage", {})
        except GatewayError:
            raise
        except Exception as exc:
            raise map_client_error(exc)
        u = self.normalize_usage(usage)
        yield StreamEvent("usage", {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "cached_tokens": u.cached_tokens, "cost": None})
        yield StreamEvent("response.completed", {"finish_reason": finish, "model_used": spec.provider_model_id, "notes": notes})
