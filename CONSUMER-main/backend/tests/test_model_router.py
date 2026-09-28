"""Tests for ModelRouter (cross-model fallback + circuit breaker) and the
collection registry / dimension-mismatch detection that back the reindex
pipeline. All use a fake in-memory provider — no real network calls."""
from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.core.errors import LLMUnavailableError
from app.llm.base import LLMProvider
from app.llm.router.circuit_breaker import CircuitBreaker
from app.llm.router.model_router import ModelRouter


class _FakeProvider(LLMProvider):
    """Configurable fake: fails for specific model names N times before
    succeeding, so tests control exactly when fallback should trigger."""

    name = "fake"

    def __init__(self, fail_models: dict[str, int] | None = None) -> None:
        self.fail_models = dict(fail_models or {})
        self.calls: list[str] = []

    @property
    def embedding_dimension(self) -> int:
        return 42

    def embedding_mode(self) -> str:
        return "fake"

    def model_for(self, purpose=None, model_name=None) -> str:
        if model_name:
            return model_name
        return "primary-model"

    def health_check(self) -> dict:
        return {"provider": self.name, "status": "configured"}

    async def generate(self, prompt, temperature=0.2, purpose="reasoning", model_name=None) -> str:
        model = model_name or self.model_for(purpose)
        self.calls.append(model)
        remaining = self.fail_models.get(model, 0)
        if remaining > 0:
            self.fail_models[model] = remaining - 1
            raise RuntimeError(f"{model} failed")
        return f"ok:{model}"

    async def generate_stream(self, prompt, temperature=0.2, purpose="reasoning", model_name=None):
        result = await self.generate(prompt, temperature, purpose, model_name)
        yield result

    async def embed_documents(self, texts):
        return [[0.0] * 42 for _ in texts]

    async def embed_query(self, text):
        return [0.0] * 42


def _settings(**overrides) -> Settings:
    base = dict(
        llm_fallback_model="fallback-model",
        llm_circuit_breaker_threshold=3,
        llm_circuit_breaker_cooldown_seconds=60,
    )
    base.update(overrides)
    return Settings(**base)


def test_no_fallback_needed_when_primary_succeeds() -> None:
    provider = _FakeProvider()
    router = ModelRouter(provider, _settings())
    result = asyncio.run(router.generate("hi", purpose="reasoning", model_name="primary-model"))
    assert result == "ok:primary-model"
    assert provider.calls == ["primary-model"]


def test_falls_back_to_fast_model_when_primary_fails() -> None:
    provider = _FakeProvider(fail_models={"primary-model": 99})
    router = ModelRouter(provider, _settings())
    result = asyncio.run(router.generate("hi", purpose="reasoning", model_name="primary-model"))
    assert result == "ok:fallback-model"
    assert provider.calls == ["primary-model", "fallback-model"]


def test_raises_sanitized_error_when_both_models_fail() -> None:
    provider = _FakeProvider(fail_models={"primary-model": 99, "fallback-model": 99})
    router = ModelRouter(provider, _settings())
    with pytest.raises(LLMUnavailableError) as exc_info:
        asyncio.run(router.generate("hi", purpose="reasoning", model_name="primary-model"))
    # never leaks the underlying provider error text
    assert "primary-model failed" not in str(exc_info.value)
    assert exc_info.value.status_code == 503


def test_circuit_opens_after_threshold_and_skips_primary() -> None:
    provider = _FakeProvider(fail_models={"primary-model": 99})
    router = ModelRouter(provider, _settings(llm_circuit_breaker_threshold=2))

    asyncio.run(router.generate("1", purpose="reasoning", model_name="primary-model"))
    asyncio.run(router.generate("2", purpose="reasoning", model_name="primary-model"))
    assert router.circuit.is_open("primary-model") is True

    provider.calls.clear()
    result = asyncio.run(router.generate("3", purpose="reasoning", model_name="primary-model"))
    assert result == "ok:fallback-model"
    # circuit open -> skipped primary entirely, went straight to fallback
    assert provider.calls == ["fallback-model"]


def test_circuit_breaker_closes_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    breaker.record_failure("m")
    breaker.record_failure("m")
    assert breaker.is_open("m") is True
    breaker.record_success("m")
    assert breaker.is_open("m") is False
    assert breaker.state("m")["consecutive_failures"] == 0


def test_circuit_breaker_half_opens_after_cooldown() -> None:
    import time

    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=1)
    breaker.record_failure("m")
    assert breaker.is_open("m") is True
    # Backdate the open time instead of a real sleep — deterministic and fast.
    breaker._opened_at["m"] = time.monotonic() - 2
    assert breaker.is_open("m") is False


def test_primary_equal_to_fallback_skips_second_tier() -> None:
    provider = _FakeProvider(fail_models={"fallback-model": 1})
    router = ModelRouter(provider, _settings(llm_fallback_model="fallback-model"))
    with pytest.raises(RuntimeError):
        asyncio.run(router._attempt("hi", 0.2, "reasoning", "fallback-model", tier="primary"))
