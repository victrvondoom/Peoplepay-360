from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.rag.retrieval.jsonl_vector_store import JsonlVectorStore
from app.rag.retrieval.qdrant_vector_store import QdrantVectorStore
from app.rag.retrieval.vector_store import VectorStore


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.vector_store_backend == "qdrant":
        return QdrantVectorStore()
    return JsonlVectorStore()


def validate_vector_store_startup() -> None:
    settings = get_settings()
    if settings.environment == "production" and settings.vector_store_backend != "qdrant":
        raise RuntimeError("Production requires VECTOR_STORE_BACKEND=qdrant")
    if settings.vector_store_backend != "qdrant":
        return
    store = get_vector_store()
    if not isinstance(store, QdrantVectorStore):
        raise RuntimeError("VECTOR_STORE_BACKEND=qdrant but QdrantVectorStore was not selected")
    try:
        store._get_client().get_collections()
    except Exception as exc:
        raise RuntimeError(f"Qdrant health check failed at {settings.qdrant_url}: {exc}") from exc
