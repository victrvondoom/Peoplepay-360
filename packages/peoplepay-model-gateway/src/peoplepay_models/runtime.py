"""Build a configured ModelGateway from the environment (self-hosted and cloud)."""
from __future__ import annotations

import os
import threading

from .bootstrap import register_env_connections
from .gateway import ModelGateway
from .registry import default_registry
from .store import ModelStore
from .vault import EncryptedSqliteVault, MemoryVault, VaultUnavailable


def warm_system_connections(gw: ModelGateway) -> dict[str, str]:
    """One bounded validation + discovery pass for platform connections lacking a fresh catalog.

    Runs once in the background at startup so the UI shows real state ("Connected, N models" or
    "Unavailable") instead of "Not validated". It is NOT run per page view.
    """
    out: dict[str, str] = {}
    for c in gw.store.list_connections(["system"]):
        if c.enabled and gw.models.is_stale(c.id):
            try:
                out[c.id] = "ok" if gw.test_connection("system", c.id).get("ok") else "failed"
            except Exception as exc:       # warm-up must never take the gateway down
                out[c.id] = f"error:{type(exc).__name__}"
    return out


def build_from_env(env=None, *, warm: bool | None = None) -> ModelGateway:
    env = os.environ if env is None else env
    db = env.get("PEOPLEPAY_MODELS_DB", "peoplepay-models.sqlite3")
    store = ModelStore(db)
    persistent = False
    try:
        vault = EncryptedSqliteVault(env.get("PEOPLEPAY_MODELS_VAULT_DB", db + ".vault"))
        persistent = True
    except VaultUnavailable:
        # No key: user-entered credentials live in memory only (lost on restart), never in plaintext on disk.
        vault = MemoryVault()
    registry = default_registry(enable_mock=env.get("PEOPLEPAY_MODELS_ENABLE_MOCK") == "1")
    for pid in filter(None, (s.strip() for s in env.get("PEOPLEPAY_MODELS_DISABLED_PROVIDERS", "").split(","))):
        registry.disable(pid)
    gw = ModelGateway(store=store, vault=vault, registry=registry)
    gw.vault_persistent = persistent
    register_env_connections(gw, env)
    if warm is None:
        warm = env.get("PEOPLEPAY_MODELS_WARM_START", "1") != "0"
    if warm:
        gw.warm_thread = threading.Thread(target=warm_system_connections, args=(gw,), daemon=True, name="models-warm")
        gw.warm_thread.start()
    return gw
