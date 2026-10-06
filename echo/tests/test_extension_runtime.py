"""Exercise failure isolation, graph proposal boundaries and service egress limits."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from echo.extensions.contracts import (
    ExtensionContext, ExtensionError, ExtensionExecution, ExtensionManifest, ExtensionRequest, ManifestAdapter, NormalizedResult, MAX_RESULT_BYTES,
)
from echo.extensions.registry import ExtensionRegistry
from echo.extensions.runtime import ExtensionRuntime
from echo.extensions.transport import ExtensionTransportError, ServiceTransport


def manifest(extension_id: str = "reviewed-test", **updates: Any) -> ExtensionManifest:
    data = {
        "id": extension_id, "name": "Reviewed test adapter", "version": "1.0.0",
        "type": "PROVENANCE_ANALYSIS", "enabled": True,
        "license": {"spdx": "MIT"}, "runtime": {"mode": "builtin"},
        "capabilities": ["source_discovery"],
        "graph": {"write": ["Supplier", "Source", "Claim", "Evidence"]},
    }
    data.update(updates)
    return ExtensionManifest.model_validate(data)


def request() -> ExtensionRequest:
    return ExtensionRequest(request_id="test-request", capability="source_discovery")


def failure(execution: ExtensionExecution) -> ExtensionError:
    assert execution.status == "error" and execution.error is not None
    return execution.error


class Adapter(ManifestAdapter):
    def __init__(self, reviewed_manifest: ExtensionManifest, function: Any = None) -> None:
        super().__init__(reviewed_manifest)
        self.function = function
        self.calls = 0

    async def execute(self, envelope: ExtensionRequest) -> Any:
        self.calls += 1
        if self.function:
            return await self.function(envelope)
        return NormalizedResult(extension_id=self.manifest.id, extension_version=self.manifest.version)


def test_disable_isolation_and_capability_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    disabled = manifest("disabled-provider", enabled=False)
    healthy = manifest("healthy-provider", priority=5)
    registry = ExtensionRegistry()
    blocked = Adapter(disabled)
    available = Adapter(healthy)
    registry.register(disabled, blocked)
    registry.register(healthy, available)
    runtime = ExtensionRuntime(registry)
    async def scenario() -> None:
        rejected = await runtime.execute(request(), extension_id=disabled.id)
        assert failure(rejected).code == "EXTENSION_DISABLED"
        selected = await runtime.execute(request())
        assert selected.extension_id == healthy.id and selected.status == "success"
        registry.set_enabled(healthy.id, False)
        assert failure(await runtime.execute(request())).code == "CAPABILITY_UNAVAILABLE"
    asyncio.run(scenario())
    assert blocked.calls == 0 and available.calls == 1


def test_timeout_circuit_and_fallback_do_not_break_other_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    timed = manifest("timed-provider", priority=0, runtime={"mode": "builtin", "timeout_seconds": 0.02, "max_failures": 1})
    good = manifest("good-provider", priority=1)
    cancelled = []
    async def slow(_: ExtensionRequest) -> Any:
        try:
            await asyncio.sleep(2)
        finally:
            cancelled.append(True)
    registry = ExtensionRegistry()
    timed_adapter = Adapter(timed, slow)
    registry.register(timed, timed_adapter)
    registry.register(good, Adapter(good))
    runtime = ExtensionRuntime(registry)
    async def scenario() -> None:
        assert (await runtime.execute(request())).extension_id == good.id
        assert failure(runtime.recent_runs[0]).code == "EXTENSION_TIMEOUT"
        assert failure(await runtime.execute(request(), extension_id=timed.id)).code == "CIRCUIT_OPEN"
        assert (await runtime.health(good.id)).status == "healthy"
        assert (await runtime.health(timed.id)).status == "circuit_open"
    asyncio.run(scenario())
    assert cancelled and timed_adapter.calls == 1


def test_concurrency_is_bounded_for_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    reviewed = manifest(runtime={"mode": "builtin", "max_concurrency": 1, "timeout_seconds": 0.3})
    current = 0
    peak = 0
    async def work(_: ExtensionRequest) -> NormalizedResult:
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0.02)
        current -= 1
        return NormalizedResult(extension_id=reviewed.id, extension_version=reviewed.version)
    registry = ExtensionRegistry()
    registry.register(reviewed, Adapter(reviewed, work))
    runtime = ExtensionRuntime(registry)
    async def scenario() -> None:
        results = await asyncio.gather(*(runtime.execute(request()) for _ in range(4)))
        assert all(result.status == "success" for result in results)
    asyncio.run(scenario())
    assert peak == 1


def supported_payload() -> dict[str, Any]:
    return {
        "extension_id": "reviewed-test", "extension_version": "1.0.0",
        "entities": [{"ref": "supplier-a", "type": "Supplier", "name": "Alpha"}],
        "sources": [{"ref": "source-a", "url": "https://supplier.example/quote", "observed_at": "2026-10-05T00:00:00Z", "provenance_state": "KNOWN"}],
        "claims": [{"ref": "claim-a", "entity_ref": "supplier-a", "predicate": "price", "value": 120, "text": "Quote is 120", "kind": "estimate", "provenance_state": "KNOWN"}],
        "evidence": [{"ref": "evidence-a", "claim_ref": "claim-a", "source_ref": "source-a", "excerpt": "Quote 120", "observed_at": "2026-10-05T00:00:00Z", "provenance_state": "KNOWN"}],
    }


@pytest.mark.parametrize("attack", ["canonical_mutation", "producer_spoof", "dangling_source", "unknown_source", "naive_timestamp", "duplicate_evidence"])
def test_malformed_output_is_rejected_without_exception_detail(attack: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    payload = supported_payload()
    if attack == "canonical_mutation":
        payload["cypher"] = "MATCH (n) DETACH DELETE n"
    elif attack == "producer_spoof":
        payload["extension_id"] = "other-provider"
    elif attack == "dangling_source":
        payload["evidence"][0]["source_ref"] = "missing"
    elif attack == "unknown_source":
        payload["sources"][0]["provenance_state"] = "PROVENANCE_UNKNOWN"
    elif attack == "naive_timestamp":
        payload["evidence"][0]["observed_at"] = "2026-10-05T00:00:00"
    else:
        payload["evidence"].append(dict(payload["evidence"][0]))
    async def untrusted(_: ExtensionRequest) -> Any:
        return payload
    reviewed = manifest()
    registry = ExtensionRegistry()
    registry.register(reviewed, Adapter(reviewed, untrusted))
    result = asyncio.run(ExtensionRuntime(registry).execute(request()))
    assert failure(result).code == "INVALID_OUTPUT" and result.result is None
    assert "cypher" not in result.model_dump_json() and "missing" not in failure(result).message


def test_graph_permissions_and_secret_echo_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    monkeypatch.setenv("ECHO_TEST_SECRET", 'sensitive"credential')
    async def unpermitted(_: ExtensionRequest) -> Any:
        return supported_payload()
    reviewed = manifest(graph={"write": ["Source"]})
    registry = ExtensionRegistry()
    registry.register(reviewed, Adapter(reviewed, unpermitted))
    result = asyncio.run(ExtensionRuntime(registry).execute(request()))
    assert failure(result).code == "PERMISSION_DENIED"
    async def leaked(_: ExtensionRequest) -> Any:
        return {"extension_id": "reviewed-test", "extension_version": "1.0.0", "warnings": ['sensitive"credential']}
    reviewed = manifest(secrets=["ECHO_TEST_SECRET"])
    registry = ExtensionRegistry()
    registry.register(reviewed, Adapter(reviewed, leaked))
    result = asyncio.run(ExtensionRuntime(registry).execute(request()))
    assert failure(result).code == "INVALID_OUTPUT" and "sensitive" not in result.model_dump_json()


@pytest.mark.parametrize("code", ["AUTH_REQUIRED", "UPSTREAM_ARBITRARY_CODE"])
def test_extension_error_text_and_unknown_codes_cannot_escape(code: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    async def rejected(_: ExtensionRequest) -> Any:
        raise ExtensionTransportError(code, "credential=sensitive-upstream-text")
    reviewed = manifest()
    registry = ExtensionRegistry()
    registry.register(reviewed, Adapter(reviewed, rejected))
    result = asyncio.run(ExtensionRuntime(registry).execute(request()))
    assert result.status == "error" and failure(result).code in {"AUTH_REQUIRED", "EXTENSION_UNAVAILABLE"}
    assert "sensitive" not in result.model_dump_json()


def test_unknown_provenance_is_retained_honestly_and_cycles_rejected() -> None:
    payload = supported_payload()
    payload["claims"][0]["provenance_state"] = "PROVENANCE_UNKNOWN"
    payload["evidence"][0].update(provenance_state="PROVENANCE_UNKNOWN", source_ref=None, observed_at=None)
    payload["sources"] = []
    result = NormalizedResult.model_validate(payload)
    assert result.evidence[0].source_ref is None and result.claims[0].provenance_state == "PROVENANCE_UNKNOWN"
    payload["sources"] = [{"ref": "a"}, {"ref": "b"}]
    payload["source_dependencies"] = [
        {"from_source_ref": "a", "to_source_ref": "b", "type": "CITES", "explanation": "explicit citation"},
        {"from_source_ref": "b", "to_source_ref": "a", "type": "CITES", "explanation": "cyclic citation"},
    ]
    with pytest.raises(ValidationError, match="cycles"):
        NormalizedResult.model_validate(payload)


def test_dependency_disable_blocks_execution_and_env_override_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECHO_EXTENSIONS", "dependent")
    prerequisite = manifest("prerequisite")
    dependent = manifest("dependent", dependencies=["prerequisite"])
    registry = ExtensionRegistry()
    registry.register(prerequisite, Adapter(prerequisite))
    adapter = Adapter(dependent)
    registry.register(dependent, adapter)
    result = asyncio.run(ExtensionRuntime(registry).execute(request(), extension_id=dependent.id))
    assert failure(result).code == "DEPENDENCY_UNAVAILABLE" and adapter.calls == 0
    assert registry.get(prerequisite.id).enabled is False
    registry.set_enabled(prerequisite.id, True)
    assert asyncio.run(ExtensionRuntime(registry).execute(request(), extension_id=dependent.id)).status == "success"


def test_concurrent_attempts_do_not_mix_colliding_request_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    primary = manifest("primary", priority=0)
    fallback = manifest("fallback", priority=1)
    async def by_user(envelope: ExtensionRequest) -> NormalizedResult:
        await asyncio.sleep(0.01)
        if envelope.context.user_id == "alice":
            raise RuntimeError("unavailable")
        return NormalizedResult(extension_id=primary.id, extension_version=primary.version)
    registry = ExtensionRegistry()
    registry.register(primary, Adapter(primary, by_user))
    registry.register(fallback, Adapter(fallback))
    runtime = ExtensionRuntime(registry)
    async def scenario() -> None:
        alice = ExtensionRequest(request_id="shared-id", capability="source_discovery", context=ExtensionContext(user_id="alice"))
        bob = ExtensionRequest(request_id="shared-id", capability="source_discovery", context=ExtensionContext(user_id="bob"))
        (alice_result, alice_attempts), (bob_result, bob_attempts) = await asyncio.gather(
            runtime.execute_with_attempts(alice), runtime.execute_with_attempts(bob))
        assert alice_result.extension_id == fallback.id
        assert [item.extension_id for item in alice_attempts] == [primary.id, fallback.id]
        assert bob_result.extension_id == primary.id and len(bob_attempts) == 1
        assert {item.run_id for item in alice_attempts}.isdisjoint(item.run_id for item in bob_attempts)
    asyncio.run(scenario())


def test_deferred_adapter_cannot_be_activated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    registry = ExtensionRegistry()
    reviewed = manifest("deferred-provider", enabled=False)
    registry.register(reviewed)
    with pytest.raises(ValueError, match="reviewed adapter"):
        registry.set_enabled(reviewed.id, True)
    assert registry.get(reviewed.id).enabled is False


def test_manifest_loader_cannot_load_arbitrary_code_or_enable_unknown_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    directory = tmp_path / "reviewed-test"
    directory.mkdir()
    file = directory / "extension.yaml"
    data = manifest().model_dump(mode="json")
    data["module"] = "evil.imported.module"
    file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        ExtensionRegistry.load(tmp_path)
    del data["module"]
    file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("ECHO_EXTENSIONS", "not-reviewed")
    with pytest.raises(ValueError, match="unknown"):
        ExtensionRegistry.load(tmp_path)


@contextmanager
def http_service(status: int = 200, body: bytes = b'{}', headers: dict[str, str] | None = None):
    visits = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            visits.append(self.path)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_: Any) -> None:
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", visits
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def service_manifest() -> ExtensionManifest:
    return manifest(runtime={"mode": "service", "url_env": "ECHO_TEST_URL", "allowed_hosts": ["127.0.0.1"]}, permissions={"network": True})


@pytest.mark.parametrize("status,body,headers,expected", [
    (302, b"{}", {"Location": "http://unreviewed.example/secret"}, "PERMISSION_DENIED"),
    (401, b'{"error":"secret"}', {}, "AUTH_REQUIRED"),
    (429, b"{}", {}, "RATE_LIMITED"),
    (200, b"x" * (MAX_RESULT_BYTES + 1), {"Content-Length": str(MAX_RESULT_BYTES + 1)}, "INVALID_OUTPUT"),
    (200, b'{"authorization":"private"}', {}, "INVALID_OUTPUT"),
], ids=["redirect", "auth", "rate-limit", "large-response", "credential-response"])
def test_service_boundary_rejects_redirects_large_responses_and_credentials(status: int, body: bytes, headers: dict[str, str], expected: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with http_service(status, body, headers) as (url, visits):
        monkeypatch.setenv("ECHO_TEST_URL", url)
        transport = ServiceTransport(service_manifest())
        with pytest.raises(ExtensionTransportError) as captured:
            asyncio.run(transport.request("/health"))
        assert captured.value.code == expected and "secret" not in str(captured.value)
        assert visits == ["/health"]


def test_service_host_and_path_allowlist_prevents_request_driven_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = ServiceTransport(service_manifest())
    monkeypatch.setenv("ECHO_TEST_URL", "http://metadata.internal/latest")
    with pytest.raises(ExtensionTransportError) as captured:
        asyncio.run(transport.request("/health"))
    assert captured.value.code == "PERMISSION_DENIED"
    with http_service() as (url, visits):
        monkeypatch.setenv("ECHO_TEST_URL", url)
        for path in ("//metadata.internal/latest", "/%2e%2e/secret", "/health\r\nAuthorization:x"):
            with pytest.raises(ExtensionTransportError):
                asyncio.run(transport.request(path))
        assert visits == []
        assert asyncio.run(transport.request("/health")) == {}


def test_registry_readiness_uses_validated_service_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHO_EXTENSIONS", raising=False)
    monkeypatch.setenv("ECHO_TEST_URL", "http://unreviewed.example")
    reviewed = service_manifest()
    registry = ExtensionRegistry()
    adapter = Adapter(reviewed)
    registry.register(reviewed, adapter)
    assert registry.describe()[0]["configured"] is False
    result = asyncio.run(ExtensionRuntime(registry).execute(request()))
    assert failure(result).code == "PERMISSION_DENIED" and adapter.calls == 0
    monkeypatch.setenv("ECHO_TEST_URL", "http://127.0.0.1:8123")
    assert registry.describe()[0]["configured"] is True


def test_service_array_mode_is_explicit_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    with http_service(body=b'[{"value":120}]') as (url, _):
        monkeypatch.setenv("ECHO_TEST_URL", url)
        transport = ServiceTransport(service_manifest())
        assert asyncio.run(transport.request("/observations", expected_response="array")) == [{"value": 120}]
        with pytest.raises(ExtensionTransportError) as captured:
            asyncio.run(transport.request("/observations"))
        assert captured.value.code == "INVALID_OUTPUT"


def test_cancelled_dns_worker_retains_capacity_and_sends_no_late_request(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    release = threading.Event()
    original_lookup = socket.getaddrinfo
    def blocked_lookup(*args: Any, **kwargs: Any) -> Any:
        started.set()
        release.wait(timeout=1)
        return original_lookup(*args, **kwargs)
    with http_service() as (url, visits):
        monkeypatch.setenv("ECHO_TEST_URL", url)
        reviewed = service_manifest().model_copy(update={"id": "blocked-dns-worker"})
        reviewed.runtime.max_concurrency = 1
        transport = ServiceTransport(reviewed)
        monkeypatch.setattr(socket, "getaddrinfo", blocked_lookup)
        async def scenario() -> None:
            first = asyncio.create_task(transport.request("/health"))
            assert await asyncio.to_thread(started.wait, 0.2)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            with pytest.raises(ExtensionTransportError) as captured:
                await transport.request("/health")
            assert captured.value.code == "RATE_LIMITED"
            release.set()
            await asyncio.sleep(0.05)
            assert visits == []
            assert await transport.request("/health") == {}
        try:
            asyncio.run(scenario())
        finally:
            release.set()


def test_request_boundary_rejects_secrets_nonfinite_values_and_excessive_arrays() -> None:
    for untrusted in ({"api_key": "secret"}, {"price": float("nan")}, {"items": [0] * 101}):
        with pytest.raises(ValidationError):
            ExtensionRequest(request_id="test-request", capability="source_discovery", input=untrusted)
