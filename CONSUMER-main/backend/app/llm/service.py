from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.llm.base import LLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Resolve the active LLM provider from settings.llm_provider, wrapped
    with cross-model fallback/circuit-breaking (ModelRouter) and a
    read-through Redis cache (CachingLLMProvider).

    Cached so every call site shares one provider instance (and its rate
    limiter / connection reuse / circuit breaker state) for the lifetime of
    the process. Use get_raw_provider() when you need the concrete provider
    without those layers (e.g. health checks that must reflect the real
    backend, not a cached/fallback result).
    """
    settings = get_settings()
    concrete = _build_provider(settings)
    from app.llm.router.model_router import ModelRouter

    routed = ModelRouter(concrete, settings)
    from app.llm.providers.caching_provider import CachingLLMProvider

    return CachingLLMProvider(routed, settings)


def get_raw_provider() -> LLMProvider:
    """The concrete provider (Gemini or NVIDIA) with no router/cache layer."""
    return _build_provider(get_settings())


def _build_provider(settings: Settings) -> LLMProvider:
    provider = (settings.llm_provider or "gemini").strip().lower()
    if provider == "nvidia":
        from app.llm.providers.nvidia_provider import NvidiaProvider

        return NvidiaProvider(settings)
    if provider == "gemini":
        from app.llm.providers.gemini_provider import GeminiProvider

        return GeminiProvider(settings)
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Supported providers: gemini, nvidia.")


class _LazyLLMService:
    """Thin proxy so `llm_service.generate(...)` always resolves through the
    cached factory, without every call site needing to call get_llm_provider()."""

    def __getattr__(self, item):
        return getattr(get_llm_provider(), item)


llm_service = _LazyLLMService()
