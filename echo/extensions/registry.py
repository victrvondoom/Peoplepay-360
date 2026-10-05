"""Core-owned manifests and capability lookup; manifests cannot import code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from echo.extensions.contracts import ExtensionAdapter, ExtensionManifest
from echo.extensions.transport import ServiceTransport

MAX_MANIFEST_BYTES = 32_768
MAX_EXTENSIONS = 64


@dataclass
class RegisteredExtension:
    manifest: ExtensionManifest
    adapter: ExtensionAdapter | None
    enabled: bool


class ExtensionRegistry:
    def __init__(self) -> None:
        self._extensions: dict[str, RegisteredExtension] = {}
        self._enabled_override = (
            {item.strip() for item in os.environ["ECHO_EXTENSIONS"].split(",") if item.strip()}
            if "ECHO_EXTENSIONS" in os.environ else None
        )

    @classmethod
    def load(cls, directory: Path | str, adapters: Mapping[str, ExtensionAdapter] | None = None) -> "ExtensionRegistry":
        """Load only one level of extension.yaml files from a trusted core directory."""
        registry = cls()
        root = Path(directory).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("extension manifest location must be a directory")
        files = sorted(root.glob("*/extension.yaml"))
        if len(files) > MAX_EXTENSIONS:
            raise ValueError("too many extension manifests")
        for file in files:
            resolved = file.resolve(strict=True)
            if not resolved.is_relative_to(root) or file.is_symlink() or file.parent.is_symlink():
                raise ValueError("extension manifests must remain within the core-owned directory")
            if file.stat().st_size > MAX_MANIFEST_BYTES:
                raise ValueError("extension manifest exceeds the size limit")
            data = yaml.safe_load(file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("extension manifest must be an object")
            manifest = ExtensionManifest.model_validate(data)
            if file.parent.name != manifest.id:
                raise ValueError("manifest id must match its containing directory")
            registry.register(manifest, (adapters or {}).get(manifest.id))
        registry._validate_dependencies()
        if registry._enabled_override is not None and registry._enabled_override - registry._extensions.keys():
            raise ValueError("ECHO_EXTENSIONS contains an unknown extension id")
        return registry

    def register(self, manifest: ExtensionManifest, adapter: ExtensionAdapter | None = None) -> RegisteredExtension:
        manifest = ExtensionManifest.model_validate(manifest.model_dump())
        if manifest.id in self._extensions:
            raise ValueError("extension id is already registered")
        if len(self._extensions) >= MAX_EXTENSIONS:
            raise ValueError("too many registered extensions")
        if adapter is not None and set(adapter.capabilities()) != set(manifest.capabilities):
            raise ValueError("adapter capabilities do not match the reviewed manifest")
        enabled = (manifest.id in self._enabled_override if self._enabled_override is not None else manifest.enabled)
        record = RegisteredExtension(manifest=manifest, adapter=adapter, enabled=enabled)
        self._extensions[manifest.id] = record
        return record

    def _validate_dependencies(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(extension_id: str) -> None:
            if extension_id in visiting:
                raise ValueError("extension dependencies contain a cycle")
            if extension_id in visited:
                return
            visiting.add(extension_id)
            for dependency in self._extensions[extension_id].manifest.dependencies:
                if dependency not in self._extensions:
                    raise ValueError("extension dependency is not registered")
                visit(dependency)
            visiting.remove(extension_id)
            visited.add(extension_id)
        for extension_id in self._extensions:
            visit(extension_id)

    def get(self, extension_id: str) -> RegisteredExtension:
        return self._extensions[extension_id]

    def find(self, capability: str, *, enabled_only: bool = True) -> list[RegisteredExtension]:
        return sorted(
            [item for item in self._extensions.values()
             if capability in item.manifest.capabilities and (item.enabled or not enabled_only)],
            key=lambda item: (item.manifest.priority, item.manifest.id),
        )

    def set_enabled(self, extension_id: str, enabled: bool) -> RegisteredExtension:
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        record = self.get(extension_id)
        if enabled and record.adapter is None:
            raise ValueError("an extension without a reviewed adapter cannot be activated")
        record.enabled = enabled
        return record

    def dependencies_available(self, record: RegisteredExtension) -> bool:
        """Require every transitive prerequisite to be enabled and attached."""
        visited: set[str] = set()
        def available(extension_id: str) -> bool:
            if extension_id in visited:
                return False  # invalid cycles created by manual registration fail closed
            dependency = self._extensions.get(extension_id)
            if dependency is None or not dependency.enabled or dependency.adapter is None:
                return False
            visited.add(extension_id)
            result = all(available(item) for item in dependency.manifest.dependencies)
            visited.remove(extension_id)
            return result
        return all(available(item) for item in record.manifest.dependencies)

    def describe(self) -> list[dict[str, Any]]:
        rows = []
        for record in sorted(self._extensions.values(), key=lambda item: item.manifest.id):
            manifest = record.manifest
            configured = manifest.runtime.mode == "builtin" or ServiceTransport(manifest).configured
            dependencies = self.dependencies_available(record)
            reason = (
                "disabled" if not record.enabled else
                "adapter unavailable" if record.adapter is None else
                "configuration required" if not configured else
                "dependency unavailable" if not dependencies else "ready"
            )
            rows.append({
                "id": manifest.id, "name": manifest.name, "version": manifest.version,
                "type": manifest.type.value, "enabled": record.enabled,
                "capabilities": manifest.capabilities, "priority": manifest.priority,
                "upstream": manifest.upstream.model_dump(mode="json"),
                "license": manifest.license.model_dump(mode="json"),
                "runtime_mode": manifest.runtime.mode,
                "permissions": manifest.permissions.model_dump(mode="json"),
                "graph": manifest.graph.model_dump(mode="json"),
                "configured": configured, "adapter_available": record.adapter is not None,
                "dependencies_available": dependencies, "status": reason,
            })
        return rows
