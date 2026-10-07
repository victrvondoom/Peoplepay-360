"""ProviderRegistry (manifests + adapter factories) and ModelRegistry (cached catalogs)."""
from __future__ import annotations

import time
from typing import Any, Callable

from .adapters.anthropic import AnthropicAdapter
from .adapters.base import DecisionProvider, ProviderAdapter, ProviderManifest
from .adapters.bedrock import BedrockAdapter
from .adapters.decision import JevProvider, LayaProvider
from .adapters.mock import MockAdapter
from .adapters.ollama import OllamaAdapter
from .adapters.openai_compat import CustomOpenAIAdapter, NvidiaNimAdapter, OpenAIAdapter, OpenRouterAdapter
from .canonical import ProviderConnection, ProviderModelRoute
from .errors import ErrorCode, GatewayError
from .heuristics import canonical_id
from .store import ModelStore
from .transport import Transport


class ProviderRegistry:
    """Adding a provider = register(AdapterClass). Nothing else in the gateway changes."""

    def __init__(self) -> None:
        self._classes: dict[str, type] = {}
        self._disabled: set[str] = set()

    def register(self, cls: type) -> None:
        self._classes[cls.manifest.id] = cls

    def disable(self, provider_id: str) -> None:     # platform-owner kill switch
        self._disabled.add(provider_id)

    def is_enabled(self, provider_id: str) -> bool:
        return provider_id in self._classes and provider_id not in self._disabled

    def manifest(self, provider_id: str) -> ProviderManifest:
        if provider_id not in self._classes:
            raise GatewayError(ErrorCode.INVALID_REQUEST, f"unknown provider {provider_id!r}")
        return self._classes[provider_id].manifest

    def manifests(self, *, include_experimental: bool = True) -> list[ProviderManifest]:
        return [c.manifest for pid, c in self._classes.items()
                if pid not in self._disabled and (include_experimental or not c.manifest.experimental)]

    def build(self, conn: ProviderConnection, secrets: dict[str, str], transport: Transport, **kw):
        cls = self._classes.get(conn.provider_type)
        if cls is None or conn.provider_type in self._disabled:
            raise GatewayError(ErrorCode.PROVIDER_UNAVAILABLE, f"provider {conn.provider_type!r} is not available")
        return cls(conn.id, conn.configuration, secrets, transport, **kw)


def default_registry(*, enable_mock: bool = False) -> ProviderRegistry:
    r = ProviderRegistry()
    for c in (OpenAIAdapter, AnthropicAdapter, OpenRouterAdapter, BedrockAdapter, NvidiaNimAdapter,
              OllamaAdapter, CustomOpenAIAdapter, JevProvider, LayaProvider):
        r.register(c)
    if enable_mock:
        r.register(MockAdapter)
    return r


class ModelRegistry:
    """Catalog of routes per connection. Discovery results are cached; the UI never triggers discovery."""

    def __init__(self, store: ModelStore, ttl: float = 6 * 3600.0, clock: Callable[[], float] = time.time):
        self.store, self.ttl, self._clock = store, ttl, clock

    def put(self, connection_id: str, routes: list[ProviderModelRoute], error: str | None = None) -> None:
        # Link routes of the same model across providers via a conservative canonical id.
        for r in routes:
            r.canonical_model_id = canonical_id(r.provider_model_id) if r.kind == "chat" else r.provider_model_id
        # A model that vanished from discovery is kept but marked, so history still resolves.
        previous = self.store.get_catalog(connection_id)
        if previous and error is None:
            have = {r.provider_model_id for r in routes}
            for old in previous[0]:
                if old.provider_model_id not in have:
                    old.availability = "unavailable" if old.availability != "deprecated" else "deprecated"
                    old.status = "no longer listed by provider"
                    routes.append(old)
        self.store.save_catalog(connection_id, routes, error)

    def get(self, connection_id: str) -> list[ProviderModelRoute]:
        cat = self.store.get_catalog(connection_id)
        return cat[0] if cat else []

    def age(self, connection_id: str) -> float | None:
        cat = self.store.get_catalog(connection_id)
        return self._clock() - cat[1] if cat else None

    def is_stale(self, connection_id: str) -> bool:
        a = self.age(connection_id)
        return a is None or a > self.ttl

    def last_error(self, connection_id: str) -> str | None:
        cat = self.store.get_catalog(connection_id)
        return cat[2] if cat else None

    def find(self, connection_ids: list[str], selector: str) -> list[ProviderModelRoute]:
        """Resolve a user selector (route key, provider id, canonical id) to routes."""
        out = []
        for cid in connection_ids:
            for r in self.get(cid):
                if selector in (r.key, r.provider_model_id, r.canonical_model_id):
                    out.append(r)
        return out

    def by_model(self, connection_ids: list[str]) -> dict[str, list[ProviderModelRoute]]:
        groups: dict[str, list[ProviderModelRoute]] = {}
        for cid in connection_ids:
            for r in self.get(cid):
                groups.setdefault(r.canonical_model_id, []).append(r)
        return groups
