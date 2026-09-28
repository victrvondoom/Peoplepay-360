from __future__ import annotations

import tempfile
from pathlib import Path

from app.rag.retrieval.collection_registry import CollectionRegistry


def _registry() -> CollectionRegistry:
    tmp = Path(tempfile.mkdtemp()) / "registry.json"
    return CollectionRegistry(tmp)


def test_bootstrap_registers_legacy_v1_without_moving_data() -> None:
    registry = _registry()
    entry = registry.ensure_bootstrapped("banking", "proxy_banking", lambda: 768)
    assert entry["active_version"] == "v1"
    assert entry["versions"]["v1"]["collection_name"] == "proxy_banking"
    assert entry["versions"]["v1"]["dimension"] == 768
    active = registry.get_active("banking")
    assert active["collection_name"] == "proxy_banking"


def test_bootstrap_is_idempotent() -> None:
    registry = _registry()
    calls = {"n": 0}

    def detect():
        calls["n"] += 1
        return 768

    registry.ensure_bootstrapped("telecom", "proxy_telecom", detect)
    registry.ensure_bootstrapped("telecom", "proxy_telecom", detect)
    assert calls["n"] == 1  # second call short-circuits, doesn't re-detect


def test_register_and_activate_new_version_preserves_old() -> None:
    registry = _registry()
    registry.ensure_bootstrapped("ecommerce", "proxy_ecommerce", lambda: 768)
    next_label = registry.next_version_label("ecommerce")
    assert next_label == "v2"

    registry.register_version(
        "ecommerce", "v2",
        collection_name="proxy_ecommerce_v2_nvidia_1024",
        provider="nvidia", embedding_model="nvidia/nv-embedqa-e5-v5",
        dimension=1024, status="building",
    )
    # not active until explicitly activated
    assert registry.get_active("ecommerce")["version"] == "v1"

    registry.activate_version("ecommerce", "v2")
    active = registry.get_active("ecommerce")
    assert active["version"] == "v2"
    assert active["collection_name"] == "proxy_ecommerce_v2_nvidia_1024"

    # old version preserved, just deprecated — not deleted
    snapshot = registry.snapshot()
    v1 = snapshot["domains"]["ecommerce"]["versions"]["v1"]
    assert v1["collection_name"] == "proxy_ecommerce"
    assert v1["status"] == "deprecated"


def test_mark_needs_reindex() -> None:
    registry = _registry()
    registry.ensure_bootstrapped("airlines", "proxy_airlines", lambda: 768)
    registry.mark_needs_reindex("airlines", "v1")
    assert registry.get_active("airlines")["status"] == "needs_reindex"
