from __future__ import annotations

from typing import AsyncIterator

from app.core.config import Settings
from app.llm.base import LLMProvider, LLMPurpose
from app.llm.metrics import metrics
from app.services.cache import embedding_cache_key, prompt_cache_key, redis_cache


class CachingLLMProvider(LLMProvider):
    """Read-through Redis cache in front of any LLMProvider (or ModelRouter).

    Streaming is intentionally not cached — it's not meaningfully reusable
    (the caller wants tokens as they arrive) and caching a stream would mean
    buffering the whole response anyway, defeating the point of streaming.
    """

    def __init__(self, inner: LLMProvider, settings: Settings) -> None:
        self.inner = inner
        self.settings = settings
        self.name = inner.name

    @property
    def embedding_dimension(self) -> int:
        return self.inner.embedding_dimension

    def embedding_mode(self) -> str:
        return self.inner.embedding_mode()

    def model_for(self, purpose: LLMPurpose | None = None, model_name: str | None = None) -> str:
        return self.inner.model_for(purpose, model_name)

    def health_check(self) -> dict:
        return self.inner.health_check()

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> str:
        model = self.inner.model_for(purpose, model_name)
        key = prompt_cache_key(self.name, model, purpose, temperature, prompt)
        cached = await redis_cache.get_json(key)
        if cached is not None:
            metrics.increment("cache_hit.prompt")
            return cached
        metrics.increment("cache_miss.prompt")
        result = await self.inner.generate(prompt, temperature=temperature, purpose=purpose, model_name=model_name)
        await redis_cache.set_json(key, result, self.settings.cache_prompt_ttl_seconds)
        return result

    def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> AsyncIterator[str]:
        return self.inner.generate_stream(prompt, temperature=temperature, purpose=purpose, model_name=model_name)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self.inner.model_for()
        keys = [embedding_cache_key(self.name, model, text, "passage") for text in texts]
        cached_results: list[list[float] | None] = []
        for key in keys:
            cached_results.append(await redis_cache.get_json(key))

        missing_indexes = [i for i, cached in enumerate(cached_results) if cached is None]
        if missing_indexes:
            metrics.increment("cache_miss.embedding", len(missing_indexes))
            fresh = await self.inner.embed_documents([texts[i] for i in missing_indexes])
            for offset, index in enumerate(missing_indexes):
                cached_results[index] = fresh[offset]
                await redis_cache.set_json(keys[index], fresh[offset], self.settings.cache_embedding_ttl_seconds)
        if len(missing_indexes) < len(texts):
            metrics.increment("cache_hit.embedding", len(texts) - len(missing_indexes))
        return [vector for vector in cached_results if vector is not None]

    async def embed_query(self, text: str) -> list[float]:
        model = self.inner.model_for()
        key = embedding_cache_key(self.name, model, text, "query")
        cached = await redis_cache.get_json(key)
        if cached is not None:
            metrics.increment("cache_hit.embedding")
            return cached
        metrics.increment("cache_miss.embedding")
        vector = await self.inner.embed_query(text)
        await redis_cache.set_json(key, vector, self.settings.cache_embedding_ttl_seconds)
        return vector
