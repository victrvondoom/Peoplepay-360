"""Capability execution with bounded concurrency and isolated, structured failures."""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from echo.extensions.contracts import (
    ExtensionError, ExtensionExecution, ExtensionHealth, ExtensionRequest, NormalizedResult, contains_secret,
)
from echo.extensions.registry import ExtensionRegistry, RegisteredExtension
from echo.extensions.transport import ExtensionTransportError, ServiceTransport

ERROR_MESSAGES = {
    "EXTENSION_DISABLED": "Extension is disabled",
    "EXTENSION_UNAVAILABLE": "Extension execution failed",
    "EXTENSION_TIMEOUT": "Extension exceeded its time limit",
    "INVALID_INPUT": "Extension request failed its input contract",
    "INVALID_OUTPUT": "Extension result failed the normalized contract",
    "CAPABILITY_UNAVAILABLE": "Extension does not provide the requested capability",
    "DEPENDENCY_UNAVAILABLE": "An extension dependency is unavailable",
    "PERMISSION_DENIED": "Extension exceeded its reviewed permissions",
    "CIRCUIT_OPEN": "Extension failure circuit is temporarily open",
    "RATE_LIMITED": "Extension concurrency or service rate limit was reached",
    "AUTH_REQUIRED": "Extension-specific authorization is required",
    "CONFIGURATION_REQUIRED": "Extension service configuration is required",
}


@dataclass
class CircuitState:
    semaphore: asyncio.Semaphore
    failures: int = 0
    open_until: float = 0


class ExtensionRuntime:
    def __init__(self, registry: ExtensionRegistry) -> None:
        self.registry = registry
        self._states: dict[str, CircuitState] = {}
        self.recent_runs: deque[ExtensionExecution] = deque(maxlen=100)

    def _state(self, record: RegisteredExtension) -> CircuitState:
        if record.manifest.id not in self._states:
            self._states[record.manifest.id] = CircuitState(asyncio.Semaphore(record.manifest.runtime.max_concurrency))
        return self._states[record.manifest.id]

    def _finish(self, request: ExtensionRequest, record: RegisteredExtension | None, started_at: datetime,
                started_clock: float, *, result: NormalizedResult | None = None,
                code: str | None = None, message: str = "") -> ExtensionExecution:
        execution = ExtensionExecution(
            run_id=f"ext-run-{uuid4().hex}", request_id=request.request_id, capability=request.capability,
            extension_id=record.manifest.id if record else None,
            extension_version=record.manifest.version if record else None,
            status=result.status if result else "error", result=result,
            error=ExtensionError(code=code, message=message) if code else None,
            started_at=started_at, finished_at=datetime.now(timezone.utc),
            duration_ms=round((time.monotonic() - started_clock) * 1000, 3),
            input_bytes=len(request.model_dump_json().encode("utf-8")),
            output_count=sum(len(getattr(result, field)) for field in ("claims", "evidence", "sources", "entities", "observations")) if result else 0,
        )
        self.recent_runs.append(execution)
        return execution

    def _ready_error(self, record: RegisteredExtension, request: ExtensionRequest) -> tuple[str, str] | None:
        if not record.enabled:
            return "EXTENSION_DISABLED", "Extension is disabled"
        if request.capability not in record.manifest.capabilities:
            return "CAPABILITY_UNAVAILABLE", "Extension does not provide the requested capability"
        if record.adapter is None:
            return "EXTENSION_UNAVAILABLE", "No reviewed adapter is attached"
        if not self.registry.dependencies_available(record):
            return "DEPENDENCY_UNAVAILABLE", "An extension dependency is unavailable"
        if record.manifest.runtime.mode == "service":
            configuration_error = ServiceTransport(record.manifest).configuration_error
            if configuration_error:
                return configuration_error.code, ERROR_MESSAGES[configuration_error.code]
        if self._state(record).open_until > time.monotonic():
            return "CIRCUIT_OPEN", "Extension failure circuit is temporarily open"
        return None

    def _normalize(self, raw: Any, record: RegisteredExtension) -> NormalizedResult:
        # Reconstruct model objects too: frozen assumptions cannot bypass validation.
        payload = raw.model_dump(mode="json") if isinstance(raw, NormalizedResult) else raw
        result = NormalizedResult.model_validate(payload)
        if result.extension_id != record.manifest.id or result.extension_version != record.manifest.version:
            raise ValueError("result producer does not match the reviewed manifest")
        writes = set(record.manifest.graph.write)
        produced_labels = {entity.type for entity in result.entities}
        if result.sources or result.source_dependencies:
            produced_labels.add("Source")
        if result.claims or result.observations:
            produced_labels.add("Claim")
        if result.evidence:
            produced_labels.add("Evidence")
        if produced_labels - writes:
            raise ExtensionTransportError("PERMISSION_DENIED", "Extension output exceeds its graph proposal permissions")
        secrets = [value for key in record.manifest.secrets if (value := os.getenv(key))]
        if contains_secret(result.model_dump(mode="json"), secrets):
            raise ValueError("result contains an extension-specific secret")
        return result

    async def _execute_one(self, request: ExtensionRequest, record: RegisteredExtension | None) -> ExtensionExecution:
        started_at = datetime.now(timezone.utc)
        started_clock = time.monotonic()
        if record is None:
            return self._finish(request, None, started_at, started_clock, code="CAPABILITY_UNAVAILABLE",
                                message="No extension provides the requested capability")
        problem = self._ready_error(record, request)
        if problem:
            return self._finish(request, record, started_at, started_clock, code=problem[0], message=problem[1])
        state = self._state(record)
        acquired = False
        try:
            try:
                await asyncio.wait_for(state.semaphore.acquire(), timeout=record.manifest.runtime.timeout_seconds)
                acquired = True
            except TimeoutError:
                return self._finish(request, record, started_at, started_clock, code="RATE_LIMITED",
                                    message="Extension concurrency limit was reached")
            # A queued request must recheck disable and circuit state before starting.
            problem = self._ready_error(record, request)
            if problem:
                return self._finish(request, record, started_at, started_clock, code=problem[0], message=problem[1])
            remaining = record.manifest.runtime.timeout_seconds - (time.monotonic() - started_clock)
            if remaining <= 0:
                return self._finish(request, record, started_at, started_clock, code="RATE_LIMITED",
                                    message="Extension execution deadline expired while queued")
            raw = await asyncio.wait_for(record.adapter.execute(request), timeout=remaining)
            result = self._normalize(raw, record)
            state.failures = 0
            state.open_until = 0
            return self._finish(request, record, started_at, started_clock, result=result)
        except TimeoutError:
            code, message = "EXTENSION_TIMEOUT", "Extension exceeded its time limit"
        except ExtensionTransportError as exc:
            code = exc.code if exc.code in ERROR_MESSAGES else "EXTENSION_UNAVAILABLE"
            message = ERROR_MESSAGES[code]
        except (ValidationError, ValueError, TypeError):
            code, message = "INVALID_OUTPUT", "Extension result failed the normalized contract"
        except Exception:  # Deliberately omit upstream exception text; it may include credentials.
            code, message = "EXTENSION_UNAVAILABLE", "Extension execution failed"
        finally:
            if acquired:
                state.semaphore.release()
        state.failures += 1
        if state.failures >= record.manifest.runtime.max_failures:
            state.open_until = time.monotonic() + record.manifest.runtime.cooldown_seconds
        return self._finish(request, record, started_at, started_clock, code=code, message=message)

    async def execute(self, request: ExtensionRequest, extension_id: str | None = None) -> ExtensionExecution:
        execution, _ = await self.execute_with_attempts(request, extension_id)
        return execution

    async def execute_with_attempts(self, request: ExtensionRequest,
                                    extension_id: str | None = None) -> tuple[ExtensionExecution, list[ExtensionExecution]]:
        """Return only this invocation's attempts, never filter shared history by user IDs."""
        request = ExtensionRequest.model_validate(request.model_dump(mode="json"))
        if extension_id is not None:
            try:
                record = self.registry.get(extension_id)
            except KeyError:
                record = None
            execution = await self._execute_one(request, record)
            return execution, [execution]
        providers = self.registry.find(request.capability)
        if not providers:
            execution = await self._execute_one(request, None)
            return execution, [execution]
        # Priority is explicit in manifests. Each failed fallback attempt retains its own run record.
        attempts = []
        for record in providers:
            execution = await self._execute_one(request, record)
            attempts.append(execution)
            if execution.status != "error":
                return execution, attempts
        return execution, attempts

    async def execute_all(self, request: ExtensionRequest) -> list[ExtensionExecution]:
        request = ExtensionRequest.model_validate(request.model_dump(mode="json"))
        providers = self.registry.find(request.capability)
        return list(await asyncio.gather(*(self._execute_one(request, record) for record in providers)))

    async def health(self, extension_id: str) -> ExtensionHealth:
        try:
            record = self.registry.get(extension_id)
        except KeyError:
            return ExtensionHealth(extension_id=extension_id, status="unavailable", message="Extension is not registered")
        if not record.enabled:
            return ExtensionHealth(extension_id=extension_id, status="disabled", message="Extension is disabled")
        if record.adapter is None or not self.registry.dependencies_available(record):
            return ExtensionHealth(extension_id=extension_id, status="unavailable", message="Adapter or dependency is unavailable")
        if record.manifest.runtime.mode == "service" and not ServiceTransport(record.manifest).configured:
            return ExtensionHealth(extension_id=extension_id, status="unconfigured", message="Service configuration is required")
        if self._state(record).open_until > time.monotonic():
            return ExtensionHealth(extension_id=extension_id, status="circuit_open", message="Failure circuit is temporarily open")
        try:
            raw = await asyncio.wait_for(record.adapter.health(), timeout=record.manifest.runtime.timeout_seconds)
            raw_payload = raw.model_dump() if isinstance(raw, ExtensionHealth) else raw
            result = ExtensionHealth.model_validate(raw_payload)
            if result.extension_id != extension_id:
                raise ValueError("health producer mismatch")
            # Health messages come from core, never from arbitrary upstream bodies.
            return ExtensionHealth(extension_id=extension_id, status=result.status,
                                   message="Extension health check completed")
        except Exception:
            return ExtensionHealth(extension_id=extension_id, status="unavailable", message="Extension health check failed")

    def statistics(self) -> dict[str, Any]:
        return {
            "retained_runs": len(self.recent_runs),
            "successes": sum(run.status in {"success", "partial"} for run in self.recent_runs),
            "failures": sum(run.status == "error" for run in self.recent_runs),
            "circuits": {extension_id: {"failures": state.failures,
                         "open": state.open_until > time.monotonic()}
                         for extension_id, state in self._states.items()},
        }
