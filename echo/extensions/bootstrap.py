"""Wire only reviewed first-party adapters. Manifests do not import code."""

from pathlib import Path

from echo.extensions.adapters.demo import DemoSourceAdapter
from echo.extensions.registry import ExtensionRegistry

MANIFEST_ROOT = Path(__file__).resolve().parents[2] / "extensions"


def build_registry() -> ExtensionRegistry:
    registry = ExtensionRegistry.load(MANIFEST_ROOT, isolate_invalid=True)
    for extension_id in ("demo-source-a", "demo-source-b"):
        if extension_id in registry.invalid_configurations:
            continue
        record = registry.get(extension_id)
        record.adapter = DemoSourceAdapter(record.manifest)
    if "inflationforge" not in registry.invalid_configurations and any(item["id"] == "inflationforge" for item in registry.describe()):
        from echo.extensions.adapters.inflationforge import InflationForgeAdapter
        record = registry.get("inflationforge")
        record.adapter = InflationForgeAdapter(record.manifest)
    if "civicmesh" not in registry.invalid_configurations and any(item["id"] == "civicmesh" for item in registry.describe()):
        from extensions.civicmesh.echo_adapter import CivicMeshEchoAdapter
        record = registry.get("civicmesh")
        record.adapter = CivicMeshEchoAdapter(record.manifest)
    return registry
