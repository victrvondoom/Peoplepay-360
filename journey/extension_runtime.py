"""Common SDK invocation gate. Provider outputs are untrusted proposals."""
import asyncio
import os
import math
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

from peoplepay_sdk import ExtensionRequest, ExtensionResult, ProviderRegistry
from journey.runtime_manifest import RuntimeManifest, load_manifests


class CapabilityRuntime:
    def __init__(self):
        self.registry = ProviderRegistry()
        self.coverage = {}
        self.health = {}
        self.traces = []
        self.manifests = {}
        self.invalid = {}
        self._active = {}
        self._lock = threading.RLock()

    def load(self, directory):
        self.manifests, self.invalid = load_manifests(directory)
        return self

    def register(self, provider, *, jurisdictions=None, input_fields=None, manifest=None):
        metadata = provider.metadata()
        manifest = manifest or self.manifests.get(metadata.id)
        if manifest is None:
            manifest = RuntimeManifest(id=metadata.id, version=metadata.version,
                capabilities={c.name: c.name for c in metadata.capabilities},
                jurisdictions=sorted(jurisdictions or []), input_fields=sorted(input_fields or []),
                upstream="explicit-host-registration", license_reference="LICENSE_UNKNOWN")
        manifest = RuntimeManifest.model_validate(manifest.model_dump(mode="json"))
        if manifest.id != metadata.id or manifest.version != metadata.version:
            raise ValueError("provider identity differs from manifest")
        if set(manifest.capabilities.values()) != {c.name for c in metadata.capabilities}:
            raise ValueError("manifest capabilities differ from implementation")
        if manifest.runtime_type == "HTTP_SERVICE" and "network.http" not in manifest.permissions:
            raise ValueError("PERMISSION_DENIED: HTTP requires network.http")
        self.registry.register(provider)
        self.manifests[metadata.id] = manifest
        if metadata.id in {v.strip() for v in os.getenv("PEOPLEPAY_DISABLED_EXTENSIONS", "").split(",")}:
            self.set_enabled(metadata.id, False)
        self.coverage[metadata.id] = {"jurisdictions": set(manifest.jurisdictions), "input_fields": set(manifest.input_fields)}

    def set_enabled(self, identifier, enabled):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        self.manifests[identifier] = self.manifests[identifier].model_copy(update={"enabled": enabled})

    def unregister_runtime_instance(self, identifier):
        self.coverage.pop(identifier, None)
        self.registry.unregister(identifier)
        self.set_enabled(identifier, False)

    def resolve(self, capability, jurisdiction):
        from peoplepay_sdk import Capability, ExtensionContext
        Capability(name=capability, description="Capability resolution")
        if jurisdiction is None:
            raise ValueError("jurisdiction is required")
        ExtensionContext(trace_id="resolution", jurisdiction=jurisdiction)
        candidates, excluded = [], []
        for identifier, manifest in sorted(self.manifests.items()):
            if capability not in manifest.capabilities and capability not in manifest.capabilities.values():
                continue
            reason = None
            if not manifest.enabled:
                reason = "DISABLED"
            elif identifier not in self.coverage:
                reason = "EXTENSION_UNAVAILABLE"
            elif jurisdiction not in manifest.jurisdictions and "*" not in manifest.jurisdictions:
                reason = "UNSUPPORTED_JURISDICTION"
            if reason:
                excluded.append({"extension_id": identifier, "reason": reason})
            else:
                candidates.append(identifier)
        candidates.sort(key=lambda i: (self.manifests[i].priority, self.manifests[i].fallback_rank, i))
        return {"capability": capability, "jurisdiction": jurisdiction, "candidates": candidates,
                "excluded": excluded, "selected_provider": candidates[0] if candidates else None,
                "fallback_providers": candidates[1:], "reason": "Enabled jurisdiction match ordered by priority, fallback rank and ID"}

    def describe(self):
        rows = []
        for identifier, manifest in sorted(self.manifests.items()):
            rows.append({**manifest.model_dump(mode="json"),
                "status": "INVALID_CONFIGURATION" if identifier in self.invalid else "DISABLED" if not manifest.enabled else "UNAVAILABLE" if identifier not in self.coverage else self.health.get(identifier, {}).get("status", "NOT_CHECKED").upper(),
                "health": self.health.get(identifier, {}),
                "last_invocation": next((t for t in reversed(self.traces) if t["extension_id"] == identifier), None)})
        return rows + [{"id": i, **v} for i, v in sorted(self.invalid.items()) if i not in self.manifests]

    async def invoke(self, request, jurisdiction, *, timeout=15, extension_id=None):
        if not isinstance(timeout, (float, int)) or isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("bounded invocation deadline required")
        deadline = time.perf_counter() + timeout
        request = ExtensionRequest.model_validate(request.model_dump(mode="json"))
        if request.context.jurisdiction and request.context.jurisdiction != jurisdiction:
            raise ValueError("jurisdiction context mismatch")
        route = self.resolve(request.capability, jurisdiction)
        candidates = route["candidates"]
        if extension_id is not None:
            candidates = [i for i in candidates if i == extension_id]
        if not candidates:
            mismatch = any(e["reason"] == "UNSUPPORTED_JURISDICTION" for e in route["excluded"])
            return None, {"status": "UNSUPPORTED_JURISDICTION" if mismatch else "EXTENSION_UNAVAILABLE", "providers": [], "routing": route}
        failures = []
        for identifier in candidates:
            manifest = self.manifests[identifier]
            provider = self.registry.get(identifier)
            if set(request.input) - set(manifest.input_fields) or set(request.constraints) - set(manifest.constraint_fields):
                raise ValueError("PERMISSION_DENIED: provider data scope exceeded")
            allowed = request.model_dump(mode="json")
            # Identity and transaction references are withheld unless explicitly granted.
            if "workflow.context" not in manifest.permissions:
                allowed["context"].update(user_id=None, tenant_id=None)
            if "transaction.reference.read" not in manifest.permissions:
                allowed["context"]["transaction_id"] = None
            allowed["capability"] = manifest.capabilities.get(request.capability, request.capability)
            scoped = ExtensionRequest.model_validate(allowed)
            started = time.perf_counter()
            run_id = "ext-run-" + uuid4().hex
            acquired = False
            try:
                async def call():
                    nonlocal acquired
                    while not acquired:
                        with self._lock:
                            if self._active.get(identifier, 0) < manifest.max_concurrency:
                                self._active[identifier] = self._active.get(identifier, 0) + 1
                                acquired = True
                        if not acquired:
                            await asyncio.sleep(.005)
                    if not self.manifests[identifier].enabled or identifier not in self.coverage:
                        raise ConnectionError("provider disabled while waiting")
                    from peoplepay_sdk import ExtensionHealth
                    raw_health = await provider.health()
                    health = ExtensionHealth.model_validate(raw_health.model_dump(mode="json"))
                    if health.extension_id != identifier:
                        raise ValueError("health producer mismatch")
                    self.health[identifier] = {"status": health.status, "checked_at": health.checked_at.isoformat(),
                        "components": health.components, "capability_health": health.capability_health}
                    status = health.capability_health.get(request.capability, health.capability_health.get(scoped.capability, health.status))
                    if status == "unavailable":
                        raise ConnectionError("provider unavailable")
                    return await provider.execute(scoped)
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError()
                raw = await asyncio.wait_for(call(), min(remaining, manifest.timeout_seconds))
                if not self.manifests[identifier].enabled or identifier not in self.coverage:
                    raise ConnectionError("provider disabled during invocation")
                result = ExtensionResult.model_validate(raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw)
                if (result.extension_id != identifier or result.extension_version != manifest.version
                        or result.request_id != request.request_id):
                    raise ValueError("invalid provider receipt binding")
                if not result.entities and "ASSISTANCE_PROVIDER_UNAVAILABLE" in result.warnings:
                    raise ConnectionError("provider returned no usable evidence")
                received = datetime.now(timezone.utc).isoformat()
                provenance = {"extension_id": identifier, "extension_version": manifest.version,
                    "extension_run_id": run_id, "request_id": request.request_id,
                    "workflow_id": request.context.workflow_id or request.context.trace_id,
                    "received_at": received, "runtime_type": manifest.runtime_type}
                payload = result.model_dump(mode="json")
                for proposal in payload["action_proposals"]:
                    proposal["requires_human_approval"] = True
                payload["raw_result"].update(host_provenance=provenance, received_at=received)
                result = ExtensionResult.model_validate(payload)
                trace = {"extension_id": identifier, "version": manifest.version, "request_id": request.request_id,
                    "run_id": run_id, "status": result.status, "timestamp": received,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "entities": len(result.entities), "evidence": len(result.evidence), "attempt_count": len(failures)+1,
                    "failures": failures, "routing": route}
                self.traces = [*self.traces[-99:], trace]
                return result, {**trace, "providers": [identifier]}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                code = "TIMEOUT" if isinstance(exc, TimeoutError) else "INVALID_EXTENSION_RESULT" if isinstance(exc, (ValueError, TypeError)) else "EXTENSION_UNAVAILABLE"
                failure = {"extension_id": identifier, "code": code, "run_id": run_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3)}
                failures.append(failure)
                self.traces = [*self.traces[-99:], {**failure, "request_id": request.request_id, "status": "error"}]
            finally:
                if acquired:
                    with self._lock:
                        self._active[identifier] -= 1
        return None, {"status": "ASSISTANCE_PROVIDER_UNAVAILABLE" if request.capability in {"assistance_eligibility", "policy.eligibility"} else "EXTENSION_UNAVAILABLE", "providers": [], "failures": failures, "routing": route}
