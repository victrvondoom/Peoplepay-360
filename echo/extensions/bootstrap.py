"""Wire only reviewed first-party adapters. Manifests do not import code."""

from pathlib import Path

from echo.extensions.adapters.demo import DemoSourceAdapter
from echo.extensions.registry import ExtensionRegistry

MANIFEST_ROOT = Path(__file__).resolve().parents[2] / "extensions"


def build_registry() -> ExtensionRegistry:
    registry = ExtensionRegistry.load(MANIFEST_ROOT)
    for extension_id in ("demo-source-a", "demo-source-b"):
        record = registry.get(extension_id)
        record.adapter = DemoSourceAdapter(record.manifest)
    if any(item["id"] == "inflationforge" for item in registry.describe()):
        from echo.extensions.adapters.inflationforge import InflationForgeAdapter
        record = registry.get("inflationforge")
        record.adapter = InflationForgeAdapter(record.manifest)
    return registry
