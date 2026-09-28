from __future__ import annotations

import logging
import time
from typing import AsyncIterator

from app.core.config import Settings
from app.core.errors import LLMUnavailableError
from app.llm.base import LLMProvider, LLMPurpose
from app.llm.metrics import metrics
from app.llm.router.circuit_breaker import CircuitBreaker
from app.llm.runtime_overrides import runtime_overrides

logger = logging.getLogger("app.llm.router")


class ModelRouter(LLMProvider):
    """Wraps a concrete LLMProvider's completion path with cross-model
    fallback and a circuit breaker, so a struggling "optional" large model
    degrades to the reliable fast default instead of failing the request.

    Retry-with-backoff for a single model is the underlying provider's job
    (see app.llm.observability.build_retrying, driven by MAX_RETRIES); this
    layer only decides whether to keep trying the requested model or drop to
    the fallback model, and never lets a raw provider exception reach the
    caller.

    Embeddings pass straight through — the fallback concept applies to
    completions, where a slower/larger model can be swapped for a faster one
    without changing the caller's contract. Swapping embedding models
    mid-flight would produce vectors of a different dimension, which is
    handled explicitly by the reindex/versioning system instead.
    """

    def __init__(self, provider: LLMProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings
        self.name = provider.name
        self.circuit = CircuitBreaker(
            failure_threshold=settings.llm_circuit_breaker_threshold,
            cooldown_seconds=settings.llm_circuit_breaker_cooldown_seconds,
        )

    @property
    def embedding_dimension(self) -> int:
        return self.provider.embedding_dimension

    def embedding_mode(self) -> str:
        return self.provider.embedding_mode()

    def model_for(self, purpose: LLMPurpose | None = None, model_name: str | None = None) -> str:
        override = runtime_overrides.model_for(self.provider.name, purpose)
        if override:
            return override
        return self.provider.model_for(purpose, model_name)

    def health_check(self) -> dict:
        health = dict(self.provider.health_check())
        health["circuit_breaker"] = self.circuit.snapshot()
        return health

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> str:
        primary_model = self.model_for(purpose, model_name)
        fallback_model = self.settings.llm_fallback_model

        if primary_model == fallback_model:
            # Already the fast/reliable default (the common case post-migration) —
            # no separate fallback tier to drop to.
            return await self._attempt(prompt, temperature, purpose, primary_model, tier="primary")

        if not self.circuit.is_open(primary_model):
            try:
                result = await self._attempt(prompt, temperature, purpose, primary_model, tier="primary")
                self.circuit.record_success(primary_model)
                return result
            except Exception as exc:
                self.circuit.record_failure(primary_model)
                metrics.increment("fallback_count")
                logger.warning(
                    "model_router_fallback provider=%s primary=%s fallback=%s reason=%s",
                    self.provider.name, primary_model, fallback_model, repr(exc),
                )
        else:
            metrics.increment("fallback_count")
            metrics.increment("circuit_breaker_open_skips")
            logger.info(
                "model_router_circuit_open provider=%s primary=%s -> routing directly to fallback=%s",
                self.provider.name, primary_model, fallback_model,
            )

        try:
            return await self._attempt(prompt, temperature, purpose, fallback_model, tier="fallback")
        except Exception as exc:
            metrics.increment("llm_unavailable_count")
            logger.error(
                "model_router_exhausted provider=%s primary=%s fallback=%s reason=%s",
                self.provider.name, primary_model, fallback_model, repr(exc),
            )
            raise LLMUnavailableError() from exc

    async def _attempt(self, prompt: str, temperature: float, purpose: LLMPurpose, model_name: str, tier: str) -> str:
        start = time.monotonic()
        try:
            result = await self.provider.generate(prompt, temperature=temperature, purpose=purpose, model_name=model_name)
        finally:
            metrics.record_latency(f"router.{tier}", (time.monotonic() - start) * 1000)
        return result

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> AsyncIterator[str]:
        primary_model = self.model_for(purpose, model_name)
        fallback_model = self.settings.llm_fallback_model
        target_model = primary_model

        if primary_model != fallback_model and self.circuit.is_open(primary_model):
            target_model = fallback_model
            metrics.increment("fallback_count")

        try:
            async for chunk in self.provider.generate_stream(prompt, temperature=temperature, purpose=purpose, model_name=target_model):
                yield chunk
            if target_model == primary_model:
                self.circuit.record_success(primary_model)
            return
        except Exception as exc:
            if target_model == primary_model and primary_model != fallback_model:
                self.circuit.record_failure(primary_model)
                metrics.increment("fallback_count")
                logger.warning("model_router_stream_fallback provider=%s primary=%s reason=%s", self.provider.name, primary_model, repr(exc))
                try:
                    async for chunk in self.provider.generate_stream(prompt, temperature=temperature, purpose=purpose, model_name=fallback_model):
                        yield chunk
                    return
                except Exception as fallback_exc:
                    metrics.increment("llm_unavailable_count")
                    raise LLMUnavailableError() from fallback_exc
            metrics.increment("llm_unavailable_count")
            raise LLMUnavailableError() from exc

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self.provider.embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return await self.provider.embed_query(text)
