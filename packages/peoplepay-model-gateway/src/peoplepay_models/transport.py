"""HTTP transport: guarded, no redirects, bounded, injectable for tests."""
from __future__ import annotations

import http.client
import json
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator
from urllib.parse import urlparse

from .errors import ErrorCode, GatewayError, redact
from .netguard import NetPolicy, validate_url

MAX_BODY = 32 * 1024 * 1024


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    lines: Iterator[bytes] | None = None   # set when streaming

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8") or "null")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "response was not valid JSON") from exc


class Transport:
    def request(self, method: str, url: str, *, headers: dict[str, str] | None = None,
                body: bytes | None = None, timeout: float = 30.0, stream: bool = False,
                trust_private: bool = False) -> HttpResponse:
        raise NotImplementedError


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class HttpTransport(Transport):
    def __init__(self, policy: NetPolicy | None = None):
        self.policy = policy or NetPolicy.from_env()

    def request(self, method, url, *, headers=None, body=None, timeout=30.0, stream=False, trust_private=False):
        policy = self.policy
        host, port, ip = validate_url(url, policy)
        p = urlparse(url)
        path = (p.path or "/") + (f"?{p.query}" if p.query else "")
        cls = _PinnedHTTPSConnection if p.scheme == "https" else _PinnedHTTPConnection
        conn = cls(host, port, ip, timeout)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
        except (socket.timeout, TimeoutError) as exc:
            conn.close()
            raise GatewayError(ErrorCode.TIMEOUT, f"timed out calling {host}") from exc
        except (OSError, http.client.HTTPException) as exc:
            conn.close()
            code = ErrorCode.LOCAL_PROVIDER_OFFLINE if isinstance(exc, ConnectionRefusedError) else ErrorCode.PROVIDER_UNAVAILABLE
            raise GatewayError(code, f"cannot reach {host}: {type(exc).__name__}") from exc
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        if stream and 200 <= resp.status < 300:
            def gen():
                try:
                    while True:
                        line = resp.readline(1 << 20)
                        if not line:
                            return
                        yield line
                except (socket.timeout, TimeoutError) as exc:
                    raise GatewayError(ErrorCode.TIMEOUT, "stream stalled") from exc
                finally:
                    conn.close()
            return HttpResponse(resp.status, hdrs, b"", gen())
        data = resp.read(MAX_BODY + 1)
        conn.close()
        if len(data) > MAX_BODY:
            raise GatewayError(ErrorCode.INVALID_RESPONSE, "response too large")
        return HttpResponse(resp.status, hdrs, data)


class FakeTransport(Transport):
    """Deterministic transport for tests: ``handler(method, url, headers, body_json) -> (status, obj|str|bytes, headers)``.

    Records every call so tests can assert (e.g.) that a cloud URL was never hit.
    """

    def __init__(self, handler: Callable | None = None):
        self.handler = handler
        self.calls: list[dict] = []

    def request(self, method, url, *, headers=None, body=None, timeout=30.0, stream=False, trust_private=False):
        parsed = None
        if body:
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = None
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "json": parsed, "stream": stream})
        if self.handler is None:
            raise GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, "no fake handler")
        out = self.handler(method, url, dict(headers or {}), parsed)
        if isinstance(out, Exception):
            raise out
        status, payload, *rest = out
        hdrs = rest[0] if rest else {}
        if isinstance(payload, (dict, list)):
            raw = json.dumps(payload).encode()
        elif isinstance(payload, str):
            raw = payload.encode()
        else:
            raw = payload
        if stream and 200 <= status < 300:
            return HttpResponse(status, hdrs, b"", iter(raw.splitlines(keepends=True)))
        return HttpResponse(status, hdrs, raw)


def classify_http(status: int, body: bytes | str = b"", headers: dict[str, str] | None = None,
                  *, local: bool = False) -> GatewayError:
    """Map an HTTP failure to a canonical error. Body text is sanitized."""
    headers = headers or {}
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    low = text.lower()
    retry_after = None
    ra = headers.get("retry-after")
    if ra:
        try:
            retry_after = float(ra)
        except ValueError:
            retry_after = None
    detail = redact(text, limit=300)
    if status in (401, 403):
        if "model" in low and ("access" in low or "not enabled" in low):
            return GatewayError(ErrorCode.MODEL_UNAVAILABLE, detail, http_status=status)
        return GatewayError(ErrorCode.INVALID_CREDENTIALS, detail, http_status=status)
    if status == 402 or "insufficient_quota" in low or "credit balance" in low or "quota" in low and status == 429 and "exceeded" in low:
        return GatewayError(ErrorCode.QUOTA_EXHAUSTED, detail, http_status=status, retry_after=retry_after)
    if status == 429:
        return GatewayError(ErrorCode.RATE_LIMITED, detail, http_status=status, retry_after=retry_after)
    if status in (404, 410):
        return GatewayError(ErrorCode.MODEL_NOT_FOUND, detail, http_status=status)
    if status == 413 or "context length" in low or "context_length" in low or "too many tokens" in low or "maximum context" in low:
        return GatewayError(ErrorCode.CONTEXT_TOO_LARGE, detail, http_status=status)
    if status in (408, 504):
        return GatewayError(ErrorCode.TIMEOUT, detail, http_status=status)
    if status == 529 or status == 503:
        return GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, detail, http_status=status, retry_after=retry_after)
    if status >= 500:
        return GatewayError(ErrorCode.SERVER_ERROR, detail, http_status=status)
    return GatewayError(ErrorCode.INVALID_REQUEST, detail, http_status=status)
