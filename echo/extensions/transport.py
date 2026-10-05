"""Bounded HTTP transport for reviewed service adapters, with no redirects."""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import socket
import threading
import time
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from echo.extensions.contracts import ExtensionManifest, MAX_REQUEST_BYTES, MAX_RESULT_BYTES, contains_secret, validate_json


class ExtensionTransportError(Exception):
    """Static errors keep service responses, endpoint credentials and secrets private."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ServiceTransport:
    _worker_limits: dict[str, threading.BoundedSemaphore] = {}
    _worker_lock = threading.Lock()

    def __init__(self, manifest: ExtensionManifest) -> None:
        self.manifest = manifest
        with self._worker_lock:
            if manifest.id not in self._worker_limits:
                self._worker_limits[manifest.id] = threading.BoundedSemaphore(manifest.runtime.max_concurrency)
        self._worker_limit = self._worker_limits[manifest.id]

    def _configuration(self) -> tuple[str, str, int | None, str, str | None]:
        manifest = self.manifest
        if manifest.runtime.mode != "service" or not manifest.permissions.network:
            raise ExtensionTransportError("PERMISSION_DENIED", "Service network permission is required")
        endpoint = os.getenv(manifest.runtime.url_env or "")
        if not endpoint:
            raise ExtensionTransportError("CONFIGURATION_REQUIRED", "Extension service URL is not configured")
        try:
            parts = urlsplit(endpoint)
            if (parts.scheme not in {"http", "https"} or not parts.hostname
                    or parts.username or parts.password or parts.query or parts.fragment
                    or any(char in endpoint for char in "\r\n\\")
                    or parts.hostname.lower() not in manifest.runtime.allowed_hosts):
                raise ValueError("service URL is outside the reviewed allowlist")
            port = parts.port
            if any(segment == ".." for segment in unquote(parts.path).split("/")):
                raise ValueError("service base path cannot traverse directories")
        except ValueError as exc:
            raise ExtensionTransportError("PERMISSION_DENIED", "Extension service URL is outside the configured host allowlist") from exc
        secret = None
        if manifest.runtime.auth_secret_env:
            secret = os.getenv(manifest.runtime.auth_secret_env)
            if not secret:
                raise ExtensionTransportError("AUTH_REQUIRED", "Extension-specific credential is not configured")
            if "\r" in secret or "\n" in secret:
                raise ExtensionTransportError("AUTH_REQUIRED", "Extension credential is invalid")
        return parts.scheme, parts.hostname, port, parts.path.rstrip("/"), secret

    @property
    def configured(self) -> bool:
        return self.configuration_error is None

    @property
    def configuration_error(self) -> ExtensionTransportError | None:
        try:
            self._configuration()
            return None
        except ExtensionTransportError as exc:
            return exc

    async def request(self, path: str, payload: dict[str, Any] | None = None, *, method: str | None = None,
                      expected_response: Literal["object", "array"] = "object") -> dict[str, Any] | list[Any]:
        operation = _TransportOperation()
        try:
            return await asyncio.to_thread(self._request, path, payload, method, expected_response, operation)
        except asyncio.CancelledError:
            operation.abort()
            raise

    def _request(self, path: str, payload: dict[str, Any] | None, method: str | None,
                 expected_response: str, operation: "_TransportOperation") -> dict[str, Any] | list[Any]:
        if expected_response not in {"object", "array"}:
            raise ExtensionTransportError("INVALID_INPUT", "Extension response shape is invalid")
        scheme, hostname, port, base_path, secret = self._configuration()
        parts = urlsplit(path)
        if (len(path) > 2400 or not path.startswith("/") or path.startswith("//")
                or parts.scheme or parts.netloc or parts.fragment
                or any(char in path for char in "\r\n\\")
                or any(segment == ".." for segment in unquote(parts.path).split("/"))):
            raise ExtensionTransportError("PERMISSION_DENIED", "Extension service path is invalid")
        selected_method = method or ("POST" if payload is not None else "GET")
        if selected_method not in {"GET", "POST"}:
            raise ExtensionTransportError("PERMISSION_DENIED", "Extension service method is not supported")
        data = None
        if payload is not None:
            try:
                validate_json(payload, maximum_bytes=MAX_REQUEST_BYTES)
                data = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
            except (ValueError, TypeError) as exc:
                raise ExtensionTransportError("INVALID_INPUT", "Extension service request is invalid") from exc
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        deadline = time.monotonic() + self.manifest.runtime.timeout_seconds
        connection_type = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        connection = connection_type(hostname, port=port, timeout=self.manifest.runtime.timeout_seconds)
        if not self._worker_limit.acquire(blocking=False):
            raise ExtensionTransportError("RATE_LIMITED", "Extension service worker limit was reached")
        operation.connection = connection
        timer = threading.Timer(self.manifest.runtime.timeout_seconds, operation.abort)
        timer.daemon = True
        timer.start()
        try:
            if operation.cancelled.is_set():
                raise TimeoutError("extension transport was cancelled")
            connection.connect()
            operation.sock = connection.sock
            connection.auto_open = False  # cancellation must never trigger an implicit reconnect
            if operation.cancelled.is_set():
                operation.abort()
                raise TimeoutError("extension transport was cancelled")
            if operation.sock:
                operation.sock.settimeout(max(0.001, deadline - time.monotonic()))
            connection.request(selected_method, base_path + path, body=data, headers=headers)
            response = connection.getresponse()
            if response.status in {401, 403}:
                raise ExtensionTransportError("AUTH_REQUIRED", "Extension service requires authorized credentials")
            if response.status == 429:
                raise ExtensionTransportError("RATE_LIMITED", "Extension service rate limit was reached")
            if 300 <= response.status < 400:
                raise ExtensionTransportError("PERMISSION_DENIED", "Extension service redirects are not permitted")
            if not 200 <= response.status < 300:
                raise ExtensionTransportError("EXTENSION_UNAVAILABLE", "Extension service returned an unsuccessful response")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ExtensionTransportError("INVALID_OUTPUT", "Compressed extension responses are not supported")
            content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise ExtensionTransportError("INVALID_OUTPUT", "Extension service response must be JSON")
            declared = response.getheader("Content-Length")
            if declared is not None and (not declared.isdigit() or int(declared) > MAX_RESULT_BYTES):
                raise ExtensionTransportError("INVALID_OUTPUT", "Extension service response exceeds the size limit")
            chunks: list[bytes] = []
            size = 0
            while True:
                # HTTP/1.0 transfers socket ownership to HTTPResponse. Reading
                # the last declared byte closes that socket through response.fp.
                # Stop before setting a timeout on the now-closed socket.
                if response.isclosed():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0 or operation.cancelled.is_set():
                    raise TimeoutError("extension transport deadline exceeded")
                if operation.sock:
                    operation.sock.settimeout(remaining)
                chunk = response.read1(min(16_384, MAX_RESULT_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESULT_BYTES:
                    raise ExtensionTransportError("INVALID_OUTPUT", "Extension service response exceeds the size limit")
                chunks.append(chunk)
            if operation.cancelled.is_set() or time.monotonic() > deadline:
                raise TimeoutError("extension transport deadline exceeded")
            if declared is not None and int(declared) != size:
                raise ExtensionTransportError("INVALID_OUTPUT", "Extension service response was incomplete")
            try:
                result = json.loads(b"".join(chunks).decode("utf-8"))
                if not isinstance(result, dict if expected_response == "object" else list):
                    raise ValueError("response has an unexpected JSON shape")
                validate_json(result, maximum_bytes=MAX_RESULT_BYTES)
                if secret and contains_secret(result, [secret]):
                    raise ValueError("response contains the extension credential")
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise ExtensionTransportError("INVALID_OUTPUT", "Extension service response failed the JSON boundary") from exc
            return result
        except (TimeoutError, socket.timeout) as exc:
            raise ExtensionTransportError("EXTENSION_TIMEOUT", "Extension service exceeded its time limit") from exc
        except (OSError, http.client.HTTPException) as exc:
            if operation.cancelled.is_set():
                raise ExtensionTransportError("EXTENSION_TIMEOUT", "Extension service exceeded its time limit") from exc
            raise ExtensionTransportError("EXTENSION_UNAVAILABLE", "Extension service could not be reached") from exc
        finally:
            timer.cancel()
            connection.close()
            self._worker_limit.release()


class _TransportOperation:
    """Interrupt sockets and retain capacity until the actual worker exits."""

    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self.connection: http.client.HTTPConnection | None = None
        self.sock: socket.socket | None = None

    def abort(self) -> None:
        self.cancelled.set()
        active_socket = self.sock or (self.connection.sock if self.connection else None)
        if active_socket:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self.connection:
            self.connection.close()
