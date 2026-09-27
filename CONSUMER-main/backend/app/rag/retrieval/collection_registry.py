from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings

REGISTRY_PATH = Path("datasets") / "vector_embeddings" / "collection_registry.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CollectionRegistry:
    """Tracks, per domain, which physical vector-store collection is the
    active one and what every known version looks like (provider, embedding
    model, dimension, chunk count, status).

    This is what makes "version collections instead of recreating them"
    real: a domain's active collection can be swapped (v1 -> v2) only after
    the new version is built and verified, with the old version's data left
    untouched in case of rollback.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or REGISTRY_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"domains": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"domains": {}}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _domain_entry(self, domain: str) -> dict[str, Any]:
        return self._data.setdefault("domains", {}).setdefault(domain, {"active_version": None, "versions": {}})

    def ensure_bootstrapped(self, domain: str, legacy_collection_name: str, detect_dimension) -> dict[str, Any]:
        """Register a v1 entry pointing at the pre-existing, unversioned
        collection if this domain has never been registered — no data is
        moved or renamed. `detect_dimension` is a zero-arg callable (kept
        lazy so we only touch the store when actually needed)."""
        with self._lock:
            entry = self._domain_entry(domain)
            if entry["active_version"] is not None:
                return entry
            dimension = detect_dimension()
            entry["versions"]["v1"] = {
                "collection_name": legacy_collection_name,
                "provider": "legacy",
                "embedding_model": "unknown",
                "dimension": dimension,
                "status": "unknown_dimension" if dimension is None else "active",
                "chunk_count": None,
                "created_at": _now(),
                "last_indexed": None,
            }
            entry["active_version"] = "v1"
            self._save()
            return entry

    def get_active(self, domain: str) -> dict[str, Any] | None:
        entry = self._data.get("domains", {}).get(domain)
        if not entry or not entry.get("active_version"):
            return None
        version = entry["versions"].get(entry["active_version"])
        if version is None:
            return None
        return {**version, "version": entry["active_version"]}

    def next_version_label(self, domain: str) -> str:
        entry = self._domain_entry(domain)
        existing = [int(v[1:]) for v in entry["versions"] if v.startswith("v") and v[1:].isdigit()]
        return f"v{(max(existing) + 1) if existing else 1}"

    def register_version(
        self,
        domain: str,
        version_label: str,
        *,
        collection_name: str,
        provider: str,
        embedding_model: str,
        dimension: int,
        status: str = "building",
    ) -> None:
        with self._lock:
            entry = self._domain_entry(domain)
            entry["versions"][version_label] = {
                "collection_name": collection_name,
                "provider": provider,
                "embedding_model": embedding_model,
                "dimension": dimension,
                "status": status,
                "chunk_count": 0,
                "created_at": _now(),
                "last_indexed": None,
            }
            self._save()

    def update_version(self, domain: str, version_label: str, **fields: Any) -> None:
        with self._lock:
            entry = self._domain_entry(domain)
            version = entry["versions"].get(version_label)
            if version is None:
                return
            version.update(fields)
            self._save()

    def activate_version(self, domain: str, version_label: str) -> None:
        with self._lock:
            entry = self._domain_entry(domain)
            if version_label not in entry["versions"]:
                return
            previous = entry.get("active_version")
            if previous and previous != version_label and previous in entry["versions"]:
                entry["versions"][previous]["status"] = "deprecated"
            entry["versions"][version_label]["status"] = "active"
            entry["versions"][version_label]["last_indexed"] = _now()
            entry["active_version"] = version_label
            self._save()

    def mark_needs_reindex(self, domain: str, version_label: str) -> None:
        self.update_version(domain, version_label, status="needs_reindex")

    def snapshot(self) -> dict[str, Any]:
        return self._data


_registry: CollectionRegistry | None = None
_registry_lock = threading.Lock()


def get_collection_registry() -> CollectionRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CollectionRegistry()
    return _registry
