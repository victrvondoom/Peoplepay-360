"""SDK invocation, coverage/health selection, permission gate and telemetry.

Provider code is registered explicitly. Manifest strings never execute code.
This reuses the SDK registry; ECHO retains its separate ingestion permissions.
"""
import asyncio
import time
from datetime import datetime, timezone

from peoplepay_sdk import ExtensionResult, ProviderRegistry


class CapabilityRuntime:
    def __init__(self):
        self.registry = ProviderRegistry()
        self.coverage = {}
        self.health = {}
        self.traces = []

    def register(self, provider, *, jurisdictions, input_fields):
        self.registry.register(provider)
        self.coverage[provider.metadata().id] = {"jurisdictions": set(jurisdictions), "input_fields": set(input_fields)}

    async def invoke(self, request, jurisdiction, *, timeout=15):
        candidates = sorted(self.registry.providers_for(request.capability), key=lambda p: p.metadata().id)
        covered = [p for p in candidates if jurisdiction in self.coverage[p.metadata().id]["jurisdictions"]]
        if not covered:
            return None, {"status": "UNSUPPORTED_JURISDICTION" if candidates else "EXTENSION_UNAVAILABLE", "providers": []}
        failures = []
        for provider in covered:
            metadata = provider.metadata()
            if set(request.input) - self.coverage[metadata.id]["input_fields"]:
                raise ValueError("PERMISSION_DENIED: provider data scope exceeded")
            started = time.perf_counter()
            try:
                # Same wall clock budget covers health and invocation.
                async def call():
                    health = await provider.health()
                    self.health[metadata.id] = health.model_dump(mode="json")
                    if health.status == "unavailable":
                        raise ConnectionError("provider unavailable")
                    return await provider.execute(request)
                result = await asyncio.wait_for(call(), timeout)
                result = ExtensionResult.model_validate(result.model_dump(mode="json"))
                if (result.extension_id != metadata.id or result.extension_version != metadata.version
                        or result.request_id != request.request_id):
                    raise ValueError("invalid provider receipt binding")
                if not result.entities and "ASSISTANCE_PROVIDER_UNAVAILABLE" in result.warnings:
                    raise ConnectionError("provider returned no usable evidence")
                trace = {"extension_id": metadata.id, "version": metadata.version, "request_id": request.request_id,
                         "run_id": result.raw_result.get("run_id"), "status": result.status,
                         "timestamp": datetime.now(timezone.utc).isoformat(),
                         "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                         "entities": len(result.entities), "evidence": len(result.evidence)}
                self.traces = [*self.traces[-99:], trace]
                return result, {**trace, "providers": [metadata.id]}
            except (TimeoutError, ConnectionError, ValueError, TypeError) as exc:
                failures.append({"extension_id": metadata.id, "code": "TIMEOUT" if isinstance(exc, TimeoutError) else "EXTENSION_UNAVAILABLE"})
        return None, {"status": "ASSISTANCE_PROVIDER_UNAVAILABLE", "providers": [], "failures": failures}
