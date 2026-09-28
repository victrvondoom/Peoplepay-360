from __future__ import annotations

import asyncio
import logging
from uuid import NAMESPACE_URL, uuid5

from app.core.config import get_settings
from app.llm.service import llm_service
from app.models.domain import Domain
from app.rag.retrieval.collection_registry import get_collection_registry
from app.rag.retrieval.factory import get_vector_store
from app.services.cache import chunks_cache_key, redis_cache

logger = logging.getLogger("app.rag.qdrant_service")


class QdrantService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _legacy_collection_name(self, domain: Domain) -> str:
        return f"{self.settings.qdrant_collection_prefix}_{domain.value}"

    def collection_name(self, domain: Domain) -> str:
        """Active, versioned collection name for a domain. Bootstraps a v1
        registry entry pointing at the pre-existing unversioned collection
        the first time a domain is touched, so no data is renamed/moved."""
        registry = get_collection_registry()
        store = get_vector_store()
        legacy_name = self._legacy_collection_name(domain)
        entry = registry.ensure_bootstrapped(
            domain.value, legacy_name, lambda: store.get_dimension(legacy_name)
        )
        active = registry.get_active(domain.value)
        return active["collection_name"] if active else legacy_name

    async def upsert_chunks(self, domain: Domain, document_id: str, chunks: list[str], metadata: dict) -> int:
        if not chunks:
            return 0

        vectors = await llm_service.embed_documents(chunks)
        collection_name = self.collection_name(domain)
        store = get_vector_store()
        points = [
            {
                "id": str(uuid5(NAMESPACE_URL, f"{domain.value}:{document_id}:{index}")),
                "vector": vector,
                "payload": {
                    "document_id": document_id,
                    "chunk_index": index,
                    "text": chunk,
                    "domain": domain.value,
                    **metadata,
                },
            }
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]
        # JsonlVectorStore's upsert_batch/flush do synchronous, potentially
        # large file I/O (some domain collections are 100+MB) -- calling
        # them directly from this async method blocks the entire single-
        # worker event loop for the full read/write duration, during which
        # NO other request (even a trivial one on a totally different route)
        # can be served. asyncio.to_thread() runs the blocking work on a
        # worker thread instead, so the event loop stays free.
        count = await asyncio.to_thread(store.upsert_batch, collection_name, points)
        await asyncio.to_thread(store.flush, collection_name)
        return count

    def dimension_status(self, domain: Domain) -> dict:
        """Compare the active collection's stored vector dimension against
        the currently configured provider's embedding dimension."""
        collection_name = self.collection_name(domain)
        registry = get_collection_registry()
        active = registry.get_active(domain.value)
        target_dimension = llm_service.embedding_dimension
        current_dimension = active.get("dimension") if active else None
        if current_dimension is None:
            store = get_vector_store()
            current_dimension = store.get_dimension(collection_name)
            if active and current_dimension is not None:
                registry.update_version(domain.value, active["version"], dimension=current_dimension)
        needs_reindex = current_dimension is not None and current_dimension != target_dimension
        if needs_reindex and active and active.get("status") != "needs_reindex":
            registry.mark_needs_reindex(domain.value, active["version"])
        return {
            "collection_name": collection_name,
            "current_dimension": current_dimension,
            "target_dimension": target_dimension,
            "needs_reindex": needs_reindex,
            "provider": active.get("provider") if active else "legacy",
            "embedding_model": active.get("embedding_model") if active else "unknown",
            "last_indexed": active.get("last_indexed") if active else None,
        }

    async def search(
        self, domain: Domain, query: str, limit: int = 5, filters: dict | None = None, query_vector: list[float] | None = None
    ) -> list[dict]:
        """`query_vector` lets a caller that's searching the same query text
        across many domains (e.g. global_search) embed it once and reuse the
        vector, instead of paying for a redundant embedding call per domain
        -- previously every domain in a cross-domain search re-embedded the
        identical query text from scratch, multiplying both latency and
        NVIDIA API usage by the domain count for zero benefit."""
        # dimension_status() -> collection_name() -> store.get_dimension()
        # can do a synchronous full-file load on a collection's first touch
        # (bootstrapping the registry entry) -- off the event loop, same
        # reasoning as the store.query() wrap below.
        status = await asyncio.to_thread(self.dimension_status, domain)
        if status["needs_reindex"]:
            logger.warning(
                "vector_search_skipped_dimension_mismatch domain=%s current_dim=%s target_dim=%s",
                domain.value, status["current_dimension"], status["target_dimension"],
            )
            return []

        cache_key = chunks_cache_key(domain.value, query, limit, filters)
        cached = await redis_cache.get_json(cache_key)
        if cached is not None:
            return cached

        collection_name = status["collection_name"]
        store = get_vector_store()

        import time
        from app.llm.metrics import metrics

        if query_vector is None:
            embed_start = time.monotonic()
            query_vector = await llm_service.embed_query(query)
            metrics.record_latency("embedding.query", (time.monotonic() - embed_start) * 1000)

        search_start = time.monotonic()
        # The real fix: store.query() on the JsonlVectorStore fallback does a
        # synchronous full-file load (some collections are 100+MB -- e.g.
        # health_insurance is ~156MB) PLUS a brute-force cosine-similarity
        # scan over every record, all synchronously. Calling it directly
        # from this async method blocks the entire single-worker event loop
        # for that whole duration -- on a resource-constrained deployment
        # (e.g. Render's free tier), this was confirmed live to freeze
        # every other in-flight request (even ones on unrelated routes)
        # until the search finished. asyncio.to_thread() moves the blocking
        # work to a worker thread so the event loop can keep serving other
        # requests concurrently.
        hits = await asyncio.to_thread(store.query, collection_name, query_vector, top_k=limit, filters=filters)
        metrics.record_latency(f"vector_search.{domain.value}", (time.monotonic() - search_start) * 1000)
        metrics.increment("vector_search_total")
        if hits:
            results = [
                {
                    "id": str(hit["id"]),
                    "score": float(hit["score"]),
                    "text": hit["payload"].get("text", ""),
                    "metadata": {key: value for key, value in hit["payload"].items() if key != "text"},
                }
                for hit in hits
            ]
            await redis_cache.set_json(cache_key, results, self.settings.cache_chunks_ttl_seconds)
            return results

        if self.settings.environment != "development":
            return []

        return [
            {
                "id": f"{domain.value}-sample-policy-clause",
                "score": 0.82,
                "text": "Sample retrieved clause: physician-directed diagnostic imaging may be covered when clinically justified and not excluded by policy terms.",
                "metadata": {"domain": domain.value, "source": "offline_seed", **(filters or {})},
            }
        ][:limit]

    async def search_chunks(self, domain: Domain, query: str, top_k: int = 5, filters: dict | None = None) -> list[dict]:
        return await self.search(domain, query, limit=top_k, filters=filters)

    def count(self, domain: Domain) -> int:
        return get_vector_store().count(self.collection_name(domain))


qdrant_service = QdrantService()
