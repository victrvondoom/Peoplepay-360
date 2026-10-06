"""Reviewed adapter attachment; no executable imports from manifest strings."""
import os
from pathlib import Path

from journey.extension_runtime import CapabilityRuntime
from journey.providers import GreenChainProvider, InflationForgeProvider, HttpSourceClient


def configured_runtime():
    runtime = CapabilityRuntime().load(Path(__file__).resolve().parents[1] / "extensions")
    for identifier, factory in {"greenchain": GreenChainProvider, "inflationforge": InflationForgeProvider}.items():
        manifest = runtime.manifests[identifier]
        endpoint = os.getenv(manifest.endpoint_env or "")
        if endpoint:
            try:
                runtime.register(factory(HttpSourceClient(endpoint), mode="live"))
            except (ValueError, ImportError):
                runtime.set_enabled(identifier, False)
                runtime.invalid[identifier] = {"status": "INVALID_CONFIGURATION"}
    endpoint = os.getenv("PEOPLEPAY_CIVICMESH_API_URL")
    if endpoint:
        try:
            from extensions.civicmesh.adapter import CivicMeshProvider
            runtime.register(CivicMeshProvider(HttpSourceClient(endpoint, token=os.getenv("PEOPLEPAY_CIVICMESH_TOKEN"), timeout_seconds=15)))
        except (ValueError, ImportError):
            runtime.set_enabled("civicmesh", False)
            runtime.invalid["civicmesh"] = {"status": "INVALID_CONFIGURATION"}
    disabled = {item.strip() for item in os.getenv("PEOPLEPAY_DISABLED_EXTENSIONS", "").split(",") if item.strip()}
    for identifier in disabled:
        if identifier in runtime.manifests:
            runtime.set_enabled(identifier, False)
    return runtime
