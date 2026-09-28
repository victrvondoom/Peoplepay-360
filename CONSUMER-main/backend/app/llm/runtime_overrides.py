from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any


class RuntimeOverrides:
    """In-memory model overrides that take effect on the next call — no
    process restart required. `get_settings()`/`get_llm_provider()` are both
    lru_cache'd for process lifetime, so this is the mechanism "hot model
    switching" actually goes through: ModelRouter.model_for() consults this
    before falling back to the .env-derived default.

    Per-process only (not shared across workers) — acceptable for a single
    FastAPI process; a multi-worker deployment would back this with Redis
    the same way app.services.cache mirrors metrics, which is a natural
    follow-up if/when this runs behind more than one worker.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._overrides: dict[str, str] = {}
        self._updated_at: dict[str, str] = {}

    def _key(self, provider: str, purpose: str | None) -> str:
        return f"{provider}:{purpose}" if purpose else f"{provider}:*"

    def set_model(self, provider: str, purpose: str | None, model: str) -> None:
        key = self._key(provider, purpose)
        with self._lock:
            self._overrides[key] = model
            self._updated_at[key] = datetime.now(timezone.utc).isoformat()

    def clear(self, provider: str, purpose: str | None = None) -> None:
        with self._lock:
            if purpose is None:
                for key in [k for k in self._overrides if k.startswith(f"{provider}:")]:
                    self._overrides.pop(key, None)
                    self._updated_at.pop(key, None)
            else:
                key = self._key(provider, purpose)
                self._overrides.pop(key, None)
                self._updated_at.pop(key, None)

    def model_for(self, provider: str, purpose: str | None) -> str | None:
        # A specific-purpose override wins over a provider-wide wildcard.
        specific = self._overrides.get(self._key(provider, purpose))
        if specific:
            return specific
        return self._overrides.get(self._key(provider, None))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                key: {"model": model, "updated_at": self._updated_at.get(key)}
                for key, model in self._overrides.items()
            }


runtime_overrides = RuntimeOverrides()
