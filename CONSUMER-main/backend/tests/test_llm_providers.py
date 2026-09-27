"""Unit/integration tests for the provider-agnostic LLM abstraction.

conftest.py pins ENVIRONMENT=test, DISABLE_EXTERNAL_LLM=true, and
LLM_PROVIDER=nvidia by default (matching the real active production
provider), so these tests never hit a real network — the provider-specific
tests below override settings explicitly per-test instead of relying on env
vars, and mock httpx so no real HTTP call is made even when a key is supplied.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.llm.gemini.service import gemini_service as gemini_alias
from app.llm.observability import RateLimiter, build_retrying, is_retryable
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.nvidia_provider import NvidiaProvider
from app.llm.service import _build_provider, get_llm_provider, get_raw_provider, llm_service


def _settings(**overrides) -> Settings:
    base = dict(
        environment="test",
        disable_external_llm=False,
        llm_provider="nvidia",
        nvidia_api_key="nvapi-test-key",
        nvidia_base_url="https://integrate.api.nvidia.com/v1",
        nvidia_reasoning_model="meta/llama-3.3-70b-instruct",
        nvidia_router_model="meta/llama-3.1-8b-instruct",
        nvidia_planner_model="meta/llama-3.1-8b-instruct",
        nvidia_response_model="meta/llama-3.3-70b-instruct",
        nvidia_summarization_model="meta/llama-3.1-8b-instruct",
        nvidia_ocr_model="meta/llama-3.3-70b-instruct",
        nvidia_embedding_model="nvidia/nv-embedqa-e5-v5",
        nvidia_request_timeout_seconds=5,
        nvidia_max_retries=3,
        nvidia_rate_limit_per_minute=0,  # unlimited in tests
    )
    base.update(overrides)
    return Settings(**base)


# ---- Provider factory -------------------------------------------------

def test_factory_resolves_gemini_provider() -> None:
    provider = _build_provider(_settings(llm_provider="gemini", gemini_api_key=None))
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"


def test_factory_resolves_nvidia_provider() -> None:
    provider = _build_provider(_settings(llm_provider="nvidia"))
    assert isinstance(provider, NvidiaProvider)
    assert provider.name == "nvidia"


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        _build_provider(_settings(llm_provider="not-a-real-provider"))


def test_gemini_alias_matches_configured_provider() -> None:
    # conftest pins LLM_PROVIDER=nvidia for the whole suite (the real active
    # production provider). The alias itself is provider-agnostic — it just
    # forwards to whatever's configured.
    assert gemini_alias is llm_service
    # get_llm_provider() returns the wrapped chain (cache + router); the
    # concrete provider is reachable underneath, or directly via get_raw_provider().
    wrapped = get_llm_provider()
    assert isinstance(wrapped.inner.provider, NvidiaProvider)
    assert isinstance(get_raw_provider(), NvidiaProvider)


# ---- Model routing ------------------------------------------------------

def test_gemini_model_routing_by_purpose() -> None:
    provider = GeminiProvider(_settings(llm_provider="gemini", gemini_reasoning_model="gemini-2.5-flash",
                                         gemini_router_model="gemini-2.5-flash-lite"))
    assert provider.model_for("reasoning") == "gemini-2.5-flash"
    assert provider.model_for("router") == "gemini-2.5-flash-lite"
    assert provider.model_for(None, "explicit-override") == "explicit-override"


def test_nvidia_model_routing_by_purpose() -> None:
    provider = NvidiaProvider(_settings())
    assert provider.model_for("reasoning") == "meta/llama-3.3-70b-instruct"
    assert provider.model_for("router") == "meta/llama-3.1-8b-instruct"
    assert provider.model_for("response") == "meta/llama-3.3-70b-instruct"
    assert provider.model_for(None, "explicit-override") == "explicit-override"


# ---- NVIDIA offline/dev fallback ----------------------------------------

def test_nvidia_generate_falls_back_offline_when_unconfigured() -> None:
    provider = NvidiaProvider(_settings(nvidia_api_key=None))
    result = asyncio.run(provider.generate("Draft an appeal for a denied claim", purpose="reasoning"))
    assert isinstance(result, str) and len(result) > 0


def test_nvidia_embed_falls_back_to_hash_embedding_when_unconfigured() -> None:
    provider = NvidiaProvider(_settings(nvidia_api_key=None))
    vectors = asyncio.run(provider.embed_documents(["hello world", "second chunk"]))
    assert len(vectors) == 2
    # hash-fallback dimension matches this provider's real embedding size (1024
    # for NVIDIA), not a fixed 768 — dev-mode vectors must never silently be
    # the wrong size for whichever provider produced them.
    assert all(len(v) == provider.embedding_dimension == 1024 for v in vectors)
    # deterministic: same text -> same vector
    again = asyncio.run(provider.embed_documents(["hello world"]))
    assert again[0] == vectors[0]


def test_nvidia_health_check_reports_missing_key() -> None:
    provider = NvidiaProvider(_settings(nvidia_api_key=None))
    health = provider.health_check()
    assert health["status"] == "missing_key"


def test_nvidia_health_check_reports_configured() -> None:
    provider = NvidiaProvider(_settings())
    health = provider.health_check()
    assert health["status"] == "configured"
    assert health["reasoning_model"] == "meta/llama-3.3-70b-instruct"


# ---- NVIDIA HTTP call mocking (no real network) --------------------------

class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict, request: httpx.Request | None = None) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.request = request or httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")

    def json(self) -> dict:
        return self._json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}", request=self.request,
                response=httpx.Response(self.status_code, request=self.request, json=self._json_body),
            )


def test_nvidia_generate_success_parses_content_and_usage(monkeypatch) -> None:
    calls = []

    async def fake_post(self, url, headers=None, json=None):
        calls.append((url, json))
        return _FakeResponse(200, {
            "choices": [{"message": {"content": "Draft appeal text."}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = NvidiaProvider(_settings())
    result = asyncio.run(provider.generate("Draft an appeal", purpose="reasoning"))

    assert result == "Draft appeal text."
    assert len(calls) == 1
    assert calls[0][1]["model"] == "meta/llama-3.3-70b-instruct"


def test_nvidia_generate_retries_on_429_then_succeeds(monkeypatch) -> None:
    attempts = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        attempts["count"] += 1
        if attempts["count"] < 3:
            return _FakeResponse(429, {"error": "rate limited"})
        return _FakeResponse(200, {"choices": [{"message": {"content": "OK"}}], "usage": {}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = NvidiaProvider(_settings(nvidia_max_retries=5))
    result = asyncio.run(provider.generate("hello", purpose="router"))

    assert result == "OK"
    assert attempts["count"] == 3


def test_nvidia_generate_does_not_retry_on_401_and_falls_back_offline(monkeypatch) -> None:
    attempts = {"count": 0}

    async def fake_post(self, url, headers=None, json=None):
        attempts["count"] += 1
        return _FakeResponse(401, {"error": "unauthorized"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # environment=test -> failure degrades to the offline canned response
    # instead of raising, but must NOT have retried a non-retryable 401.
    provider = NvidiaProvider(_settings(nvidia_max_retries=5))
    result = asyncio.run(provider.generate("hello", purpose="router"))

    assert attempts["count"] == 1
    assert isinstance(result, str) and len(result) > 0


def test_nvidia_generate_raises_in_production_when_call_fails(monkeypatch) -> None:
    async def fake_post(self, url, headers=None, json=None):
        return _FakeResponse(500, {"error": "boom"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = NvidiaProvider(_settings(environment="production", nvidia_max_retries=1))
    with pytest.raises(RuntimeError):
        asyncio.run(provider.generate("hello", purpose="router"))


def test_nvidia_embed_documents_success(monkeypatch) -> None:
    async def fake_post(self, url, headers=None, json=None):
        texts = json["input"]
        assert json["input_type"] == "passage"
        return _FakeResponse(200, {
            "data": [
                {"index": i, "embedding": [float(i)] * 4} for i, _ in enumerate(texts)
            ]
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = NvidiaProvider(_settings())
    vectors = asyncio.run(provider.embed_documents(["a", "b", "c"]))
    assert vectors == [[0.0] * 4, [1.0] * 4, [2.0] * 4]


def test_nvidia_embed_query_uses_query_input_type(monkeypatch) -> None:
    captured = {}

    async def fake_post(self, url, headers=None, json=None):
        captured["input_type"] = json["input_type"]
        return _FakeResponse(200, {"data": [{"index": 0, "embedding": [1.0, 2.0]}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = NvidiaProvider(_settings())
    vector = asyncio.run(provider.embed_query("how do I update my aadhaar"))
    assert vector == [1.0, 2.0]
    assert captured["input_type"] == "query"


# ---- Observability helpers -----------------------------------------------

def test_is_retryable_classifies_errors_correctly() -> None:
    request = httpx.Request("POST", "https://example.com")
    assert is_retryable(httpx.TimeoutException("timeout", request=request)) is True
    assert is_retryable(httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))) is True
    assert is_retryable(httpx.HTTPStatusError("500", request=request, response=httpx.Response(500, request=request))) is True
    assert is_retryable(httpx.HTTPStatusError("401", request=request, response=httpx.Response(401, request=request))) is False
    assert is_retryable(ValueError("not an http error")) is False


def test_build_retrying_respects_max_attempts() -> None:
    retryer = build_retrying(3)
    assert retryer.stop.max_attempt_number == 3


def test_rate_limiter_allows_burst_under_limit() -> None:
    limiter = RateLimiter(requests_per_minute=5)

    async def run():
        for _ in range(5):
            await limiter.acquire()

    asyncio.run(run())  # should not raise or hang
    assert len(limiter._timestamps) == 5


def test_rate_limiter_disabled_when_zero() -> None:
    limiter = RateLimiter(requests_per_minute=0)
    asyncio.run(limiter.acquire())
    assert limiter._timestamps == []
