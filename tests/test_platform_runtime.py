import asyncio
from datetime import datetime, timezone

import pytest
from peoplepay_sdk import Capability, ExtensionContext, ExtensionHealth, ExtensionMetadata, ExtensionRequest, ExtensionResult
from journey.extension_runtime import CapabilityRuntime
from journey.runtime_manifest import RuntimeManifest, load_manifests


class Provider:
    def __init__(self, identifier="sample", *, bad=False, fail=False, delay=0):
        self.identifier, self.bad, self.fail, self.delay = identifier, bad, fail, delay
        self.received = []

    def capabilities(self):
        return [Capability(name="price.observe", description="Read only price context")]

    def metadata(self):
        return ExtensionMetadata(id=self.identifier, name="Test", version="1.0.0", description="Boundary test", capabilities=self.capabilities())

    async def health(self):
        return ExtensionHealth(extension_id=self.identifier, status="healthy", checked_at=datetime.now(timezone.utc))

    async def execute(self, request):
        self.received.append(request)
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("secret should never appear in telemetry")
        if self.bad:
            return {"extension_id": "forged", "payment": "execute"}
        return ExtensionResult(request_id=request.request_id, extension_id=self.identifier, extension_version="1.0.0", status="success", raw_result={"host_provenance": {"extension_run_id": "forged"}})


def register(host, provider, **overrides):
    manifest = RuntimeManifest(id=provider.identifier, version="1.0.0", capabilities={"price.observe": "price.observe"}, jurisdictions=["US"], input_fields=["product"], upstream="test", license_reference="MIT", **overrides)
    host.register(provider, manifest=manifest)


def request(**kwargs):
    return ExtensionRequest(request_id="req-1", capability="price.observe", context=ExtensionContext(trace_id="workflow-1", user_id="private", transaction_id="private-txn"), input=kwargs or {"product": "chairs"})


def test_manifest_failure_isolated_and_authority_denied(tmp_path):
    directory = tmp_path / "evil"
    directory.mkdir()
    (directory / "runtime.yaml").write_text("id: evil\npermissions: [payment.execute]")
    accepted, invalid = load_manifests(tmp_path)
    assert not accepted and invalid["evil"]["status"] == "INVALID_CONFIGURATION"
    with pytest.raises(ValueError, match="PERMISSION_DENIED"):
        RuntimeManifest(id="evil", version="1.0.0", capabilities={"price.observe": "price.observe"}, jurisdictions=["US"], upstream="test", license_reference="MIT", permissions=["transaction.authorize"])


def test_disabled_and_wrong_jurisdiction_never_execute():
    host, provider = CapabilityRuntime(), Provider()
    register(host, provider)
    result, trace = asyncio.run(host.invoke(request(), "IN"))
    assert result is None and trace["status"] == "UNSUPPORTED_JURISDICTION"
    host.set_enabled("sample", False)
    result, trace = asyncio.run(host.invoke(request(), "US"))
    assert result is None and trace["routing"]["excluded"][0]["reason"] == "DISABLED"
    assert not provider.received


def test_minimized_identity_and_host_provenance():
    host, provider = CapabilityRuntime(), Provider()
    register(host, provider)
    result, trace = asyncio.run(host.invoke(request(), "US"))
    assert provider.received[0].context.user_id is None
    assert provider.received[0].context.transaction_id is None
    assert result.raw_result["host_provenance"]["extension_run_id"] == trace["run_id"] != "forged"
    assert result.raw_result["host_provenance"]["workflow_id"] == "workflow-1"
    with pytest.raises(ValueError, match="PERMISSION_DENIED"):
        asyncio.run(host.invoke(request(card_number="sensitive"), "US"))


def test_bad_result_and_failure_fallback_keep_separate_attempts():
    host = CapabilityRuntime()
    register(host, Provider("a", bad=True))
    register(host, Provider("b", fail=True))
    register(host, Provider("c"))
    result, trace = asyncio.run(host.invoke(request(), "US"))
    assert result.extension_id == "c" and trace["attempt_count"] == 3
    assert trace["failures"][0]["code"] == "INVALID_EXTENSION_RESULT"
    assert "secret" not in str(trace)


def test_timeout_bounded_and_parallel_invocations():
    host = CapabilityRuntime()
    register(host, Provider(delay=.2), timeout_seconds=.01)
    result, trace = asyncio.run(host.invoke(request(), "US"))
    assert result is None and trace["failures"][0]["code"] == "TIMEOUT"


def test_concurrency_limit_and_cancellation_release_slots():
    class ConcurrentProvider(Provider):
        active = 0
        maximum = 0
        async def execute(self, request):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                return await super().execute(request)
            finally:
                self.active -= 1
    host, provider = CapabilityRuntime(), ConcurrentProvider(delay=.02)
    register(host, provider, max_concurrency=2)
    async def exercise():
        results = await asyncio.gather(*(host.invoke(request(), "US") for _ in range(5)))
        assert all(result for result, _ in results)
        task = asyncio.create_task(host.invoke(request(), "US"))
        await asyncio.sleep(.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert host._active["sample"] == 0
    asyncio.run(exercise())
    assert provider.maximum == 2


def test_provider_order_has_no_effect_and_unregister_preserves_manifest():
    hosts = [CapabilityRuntime(), CapabilityRuntime()]
    for host, identifiers in zip(hosts, [("b", "a"), ("a", "b")]):
        for identifier in identifiers:
            register(host, Provider(identifier))
    assert hosts[0].resolve("price.observe", "US") == hosts[1].resolve("price.observe", "US")
    hosts[0].unregister_runtime_instance("a")
    assert hosts[0].manifests["a"].enabled is False
    assert hosts[0].resolve("price.observe", "US")["selected_provider"] == "b"
    register(hosts[0], Provider("a"))
    assert hosts[0].resolve("price.observe", "US")["selected_provider"] == "a"


@pytest.mark.parametrize("capability,jurisdiction", [(None, "US"), ([], "US"), ("price.observe", None), ("price.observe", "*"), ("price.observe", {})])
def test_resolution_rejects_invalid_contract_inputs(capability, jurisdiction):
    with pytest.raises(ValueError):
        CapabilityRuntime().resolve(capability, jurisdiction)


def test_bad_optional_endpoint_is_isolated_from_other_providers(monkeypatch):
    from journey.bootstrap import configured_runtime
    monkeypatch.setenv("PEOPLEPAY_GREENCHAIN_API_URL", "not-an-origin")
    monkeypatch.setenv("PEOPLEPAY_INFLATIONFORGE_API_URL", "http://127.0.0.1:8093")
    monkeypatch.delenv("PEOPLEPAY_CIVICMESH_API_URL", raising=False)
    monkeypatch.delenv("PEOPLEPAY_DISABLED_EXTENSIONS", raising=False)
    host = configured_runtime()
    assert host.resolve("price.observe", "IN")["selected_provider"] == "inflationforge"
    rows = [row for row in host.describe() if row["id"] == "greenchain"]
    assert len(rows) == 1 and rows[0]["status"] == "INVALID_CONFIGURATION"
