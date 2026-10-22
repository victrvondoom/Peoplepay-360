"""Transport-neutral API for /api/v1/models/* and /api/v1/chat/*.

``handle`` returns ``(status, body)`` where body is a dict, or ``(200, iterator)`` for
SSE. The PeoplePay HTTP gateway mounts it; the caller is already authenticated and
``owner`` is the verified user id. Secrets never appear in any response.
"""
from __future__ import annotations

import base64
import binascii
import logging
from typing import Any, Iterator
from urllib.parse import parse_qs

from . import limits
from .canonical import (Capability, DataClass, DecisionQuestion, FallbackMode, FilePart, ImagePart, InferenceRequest,
                        Message, ModelSelection, Reasoning, RoutingPolicy, TextPart)
from .errors import ErrorCode, GatewayError
from .gateway import CancelToken, ModelGateway

log = logging.getLogger(__name__)

_STATUS = {ErrorCode.INVALID_REQUEST: 400, ErrorCode.INVALID_CREDENTIALS: 422, ErrorCode.AUTHORIZATION_REQUIRED: 403,
           ErrorCode.POLICY_REJECTED: 403, ErrorCode.CUSTOM_ENDPOINT_BLOCKED: 422, ErrorCode.PRIVACY_POLICY_BLOCKED: 409,
           ErrorCode.NO_ROUTE: 409, ErrorCode.UNSUPPORTED_CAPABILITY: 409, ErrorCode.LOCAL_PROVIDER_OFFLINE: 409,
           ErrorCode.RATE_LIMITED: 429, ErrorCode.QUOTA_EXHAUSTED: 429, ErrorCode.CONTEXT_TOO_LARGE: 413,
           ErrorCode.MODEL_NOT_FOUND: 404, ErrorCode.CANCELLED: 499}


def _enum(cls, value, default=None):
    if value in (None, ""):
        return default
    try:
        return cls(value)
    except ValueError:
        raise GatewayError(ErrorCode.INVALID_REQUEST, f"invalid {cls.__name__}: {value!r}") from None


def _selection(b: dict) -> ModelSelection:
    s = b.get("selection") or {}
    if not isinstance(s, dict):
        raise GatewayError(ErrorCode.INVALID_REQUEST, "selection must be an object")
    mode = s.get("mode") or ("model" if s.get("model") else "auto")
    if mode not in ("auto", "default", "fast", "balanced", "deep", "local", "model"):
        raise GatewayError(ErrorCode.INVALID_REQUEST, "invalid selection mode")
    for field in ("model", "connection_id"):
        if s.get(field) is not None and not isinstance(s[field], str):
            raise GatewayError(ErrorCode.INVALID_REQUEST, f"selection.{field} must be a string")
    return ModelSelection(mode, s.get("model"), s.get("connection_id"), bool(s.get("one_shot")))


def _decoded_bytes(data: str, what: str) -> int:
    """Size of the decoded data, after checking that it IS well-formed base64 (not merely that it is long enough)."""
    if not isinstance(data, str):
        raise GatewayError(ErrorCode.INVALID_REQUEST, f"{what}: data_b64 must be a base64 string")
    try:
        return len(base64.b64decode(data, validate=True))
    except (binascii.Error, ValueError):
        raise GatewayError(ErrorCode.INVALID_REQUEST, f"{what}: data_b64 is not valid base64") from None


def _attachments(b: dict) -> list:
    raw = b.get("attachments")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise GatewayError(ErrorCode.INVALID_REQUEST, "attachments must be a list")
    if len(raw) > limits.MAX_ATTACHMENTS:
        raise GatewayError(ErrorCode.INVALID_REQUEST, f"at most {limits.MAX_ATTACHMENTS} attachments per request",
                           extra={"max_attachments": limits.MAX_ATTACHMENTS})
    out, total = [], 0
    for i, a in enumerate(raw):
        what = f"attachment {i + 1}"
        if not isinstance(a, dict):
            raise GatewayError(ErrorCode.INVALID_REQUEST, "invalid attachment")
        kind, data = a.get("kind"), a.get("data_b64")
        if kind not in ("image", "file") or not data:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "attachment needs kind and data_b64")
        size = _decoded_bytes(data, what)
        cap = limits.MAX_IMAGE_BYTES if kind == "image" else limits.MAX_FILE_BYTES
        if size > cap:
            raise GatewayError(ErrorCode.INVALID_REQUEST, f"{what} is {size} bytes; the limit is {cap} bytes",
                               extra={"limit_bytes": cap, "size_bytes": size})
        total += size
        if total > limits.MAX_ATTACHMENT_BYTES_TOTAL:
            raise GatewayError(ErrorCode.INVALID_REQUEST, f"attachments total more than {limits.MAX_ATTACHMENT_BYTES_TOTAL} bytes",
                               extra={"limit_bytes": limits.MAX_ATTACHMENT_BYTES_TOTAL})
        if kind == "image":
            media_type = a.get("media_type", "image/png")
            if media_type not in limits.IMAGE_TYPES:
                raise GatewayError(ErrorCode.INVALID_REQUEST, f"{what}: unsupported image type; use one of {', '.join(limits.IMAGE_TYPES)}")
            out.append(ImagePart(media_type, data))
        else:
            out.append(FilePart(str(a.get("name", "file"))[:120], str(a.get("media_type", "application/octet-stream"))[:120], data))
    return out


def _request_kwargs(b: dict) -> dict:
    kw: dict[str, Any] = {"data_class": _enum(DataClass, b.get("data_class"), DataClass.INTERNAL),
                          "routing_policy": _enum(RoutingPolicy, b.get("routing_policy")),
                          "fallback_mode": _enum(FallbackMode, b.get("fallback_mode")),
                          "reasoning": _enum(Reasoning, b.get("reasoning"), Reasoning.AUTO),
                          "task": str(b.get("task") or "chat")[:40]}
    if b.get("allow_drop_unsupported"):
        kw["metadata"] = {"allow_drop_unsupported": True}
    if b.get("max_output_tokens") is not None:
        mot = b["max_output_tokens"]
        if isinstance(mot, bool) or not isinstance(mot, int) or mot < 1:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "max_output_tokens must be a positive whole number")
        kw["max_output_tokens"] = min(mot, 64000)
    return kw


class ModelsAPI:
    def __init__(self, gateway: ModelGateway):
        self.gw = gateway

    def handle(self, method: str, parts: list[str], query: str, body: dict, owner: str):
        try:
            if method == "POST" and not isinstance(body, dict):
                raise GatewayError(ErrorCode.INVALID_REQUEST, "the request body must be a JSON object")
            return self._route(method, parts, parse_qs(query), body, owner)
        except GatewayError as e:
            return _STATUS.get(e.code, 502 if e.fallback_eligible else 400), {"error": e.to_dict()}
        except Exception:                                    # noqa: BLE001 - a bug must answer, not drop the connection
            log.exception("model API request failed unexpectedly")
            return 500, {"error": {"code": "SERVER_ERROR", "message": "The server could not complete this request."}}

    def _route(self, method, parts, q, body, owner):
        gw = self.gw
        if parts[:3] == ["api", "v1", "chat"]:
            return self._chat(method, parts[3:], body, owner)
        if parts[:3] != ["api", "v1", "models"]:
            return 404, {"error": {"message": "unknown route"}}
        p = parts[3:]
        g = method == "GET"
        if g and p == ["providers"]:
            return 200, {"providers": gw.provider_catalog(), "deployment": gw.net.mode, "vault": gw.vault_status()}
        if g and p == ["connections"]:
            return 200, {"connections": gw.health_overview(owner)}
        if method == "POST" and p == ["connections"]:
            if body.get("values") is not None and not isinstance(body["values"], dict):
                raise GatewayError(ErrorCode.INVALID_REQUEST, "values must be a JSON object")
            return 201, gw.connect(owner, str(body.get("provider_type", "")), str(body.get("display_name", "")), body.get("values") or {},
                                   alias=body.get("alias"), test=body.get("test", True))
        if method == "POST" and len(p) == 3 and p[0] == "connections":
            cid, action = p[1], p[2]
            if action == "test":
                return 200, gw.test_connection(owner, cid)
            if action == "refresh":
                r = gw.refresh_models(owner, cid)
                return 200, {"connection_id": cid, "count": len(r["models"]), "refreshed_at": r["refreshed_at"]}
            if action == "update":
                if body.get("values") is not None and not isinstance(body["values"], dict):
                    raise GatewayError(ErrorCode.INVALID_REQUEST, "values must be a JSON object")
                return 200, {"connection": gw.update_connection(owner, cid, display_name=body.get("display_name"),
                                                                enabled=body.get("enabled"), values=body.get("values"))}
            if action == "remove":
                gw.remove_connection(owner, cid)
                return 200, {"removed": cid}
        if g and p == ["catalog"]:
            first = lambda k: (q.get(k) or [None])[0]
            return 200, gw.list_models(owner, q=first("q"), caps=(first("caps") or "").split(",") if first("caps") else None,
                                       provider=first("provider"), local={"1": True, "0": False}.get(first("local") or ""),
                                       kind=first("kind"), include_unavailable=first("all") == "1")
        if method == "POST" and p == ["refresh-stale"]:
            return 200, {"result": gw.refresh_stale(owner)}
        if method == "POST" and p == ["capability-test"]:
            return 200, gw.test_capability(owner, body.get("connection_id", ""), body.get("model_id", ""), _enum(Capability, body.get("capability")))
        if g and p == ["preferences"]:
            return 200, {"preferences": gw.get_prefs(owner)}
        if method == "POST" and p == ["preferences"]:
            return 200, {"preferences": gw.set_prefs(owner, body)}
        if method == "POST" and p == ["preferences", "preset"]:
            return 200, {"preferences": gw.apply_preset(owner, str(body.get("name", "")))}
        if g and p == ["preferences", "export"]:
            return 200, gw.export_prefs(owner)
        if method == "POST" and p == ["preferences", "import"]:
            return 200, {"preferences": gw.import_prefs(owner, body)}
        if g and p == ["usage"]:
            return 200, gw.usage(owner)
        if g and p == ["health"]:
            return 200, gw.service_health()
        if method == "POST" and p == ["explain"]:
            req = InferenceRequest(messages=[Message("user", [TextPart(str(body.get("text", ""))), *_attachments(body)])],
                                   selection=_selection(body), **_request_kwargs(body))
            return 200, gw.explain(owner, req)
        if method == "POST" and p == ["switch-check"]:
            return 200, gw.check_switch(owner, str(body.get("conversation_id", "")), _selection(body))
        if method == "POST" and p == ["decide"]:
            if not isinstance(body.get("questions") or [], list) or not all(isinstance(x, dict) for x in body.get("questions") or []):
                raise GatewayError(ErrorCode.INVALID_REQUEST, "questions must be a list of objects")
            if body.get("state") is not None and not isinstance(body["state"], dict):
                raise GatewayError(ErrorCode.INVALID_REQUEST, "state must be a JSON object")
            qs = [DecisionQuestion(str(x.get("id")), str(x.get("kind", "")).upper(), str(x.get("prompt", "")), list(x.get("choices") or []),
                                   tuple(x["scale"]) if x.get("scale") else None) for x in body.get("questions") or []]
            return 200, gw.decide(owner, body.get("state") or {}, qs, local_only=bool(body.get("local_only")))
        return 404, {"error": {"message": f"no route for {method} /{'/'.join(parts)}"}}

    def _chat(self, method, p, body, owner):
        gw = self.gw
        if method == "GET" and p == ["conversations"]:
            return 200, {"conversations": gw.store.list_conversations(owner)}
        if method == "GET" and len(p) == 2 and p[0] == "conversations":
            return 200, gw.get_conversation(owner, p[1]).to_dict()
        if method == "POST" and p == []:
            text = body.get("text")
            if not isinstance(text, str) or not text.strip():
                raise GatewayError(ErrorCode.INVALID_REQUEST, "text is required")
            if len(text) > limits.MAX_TEXT_CHARS:
                raise GatewayError(ErrorCode.INVALID_REQUEST, "text is too long", extra={"limit_chars": limits.MAX_TEXT_CHARS})
            if body.get("conversation_id") is not None and not isinstance(body["conversation_id"], str):
                raise GatewayError(ErrorCode.INVALID_REQUEST, "conversation_id must be a string")
            kw = dict(conversation_id=body.get("conversation_id"), attachments=_attachments(body), selection=_selection(body), **_request_kwargs(body))
            if body.get("ephemeral"):      # playground/compare: nothing is saved to a conversation
                kw.pop("conversation_id", None)
                att = kw.pop("attachments")
                extra = kw.pop("metadata", None)
                req = InferenceRequest(messages=[Message("user", [TextPart(text), *att])], selection=kw.pop("selection"),
                                       **({"metadata": extra} if extra else {}), **kw)
                return 200, {"response": gw.infer(owner, req).to_dict()}
            if body.get("stream"):
                return 200, self._sse(owner, text, kw)
            return 200, gw.chat(owner, text, **kw)
        return 404, {"error": {"message": "unknown chat route"}}

    def _sse(self, owner: str, text: str, kw: dict) -> "SseStream":
        cancel = CancelToken()
        return SseStream(self.gw.chat_stream(owner, text, cancel=cancel, **kw), cancel)


class SseStream:
    """Iterator of canonical stream events; ``cancel()`` is called when the client goes away (stop button)."""

    def __init__(self, it: Iterator, cancel: CancelToken):
        self.it, self._cancel = it, cancel

    def __iter__(self):
        return self.it

    def cancel(self) -> None:
        self._cancel.cancel()
        close = getattr(self.it, "close", None)
        if close:
            close()
