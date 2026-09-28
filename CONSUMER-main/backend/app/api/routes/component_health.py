"""Per-component health probes: GET /health/llm, /health/embedding,
/health/qdrant, /health/neo4j, /health/supabase, /health/providers.

Each returns {status, latency_ms, model, provider}. Live probes are cheap
(short prompt / short embed / lightweight ping) and are throttled by a short
in-memory TTL cache so repeated polling doesn't burn API quota.
"""
from __future__ import annotations

import time
from typing import Any, Dict

import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.knowledge_graph.factory import get_graph_store
from app.llm.service import get_llm_provider, get_raw_provider
from app.rag.retrieval.factory import get_vector_store
from app.services.cache import redis_cache

router = APIRouter()

_probe_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}


async def _cached_probe(key: str, probe) -> Dict[str, Any]:
    settings = get_settings()
    now = time.monotonic()
    cached = _probe_cache.get(key)
    if cached and now - cached[0] < settings.health_probe_cache_ttl_seconds:
        return {**cached[1], "cached": True}
    result = await probe()
    _probe_cache[key] = (now, result)
    return {**result, "cached": False}


@router.get("/llm")
async def health_llm() -> Dict[str, Any]:
    async def probe() -> Dict[str, Any]:
        provider = get_raw_provider()
        start = time.monotonic()
        try:
            await provider.generate("Reply with OK.", temperature=0.0, purpose="router")
            status = "ready"
            error = None
        except Exception as exc:
            status = "unreachable"
            error = str(exc)[:200]
        return {
            "status": status,
            "provider": provider.name,
            "model": provider.model_for("router"),
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": error,
        }

    return await _cached_probe("llm", probe)


@router.get("/embedding")
async def health_embedding() -> Dict[str, Any]:
    async def probe() -> Dict[str, Any]:
        provider = get_raw_provider()
        start = time.monotonic()
        try:
            vector = await provider.embed_query("health check")
            status = "ready" if vector else "degraded"
            error = None
        except Exception as exc:
            status = "unreachable"
            error = str(exc)[:200]
        return {
            "status": status,
            "provider": provider.name,
            "model": get_settings().nvidia_embedding_model if provider.name == "nvidia" else get_settings().embedding_model,
            "dimension": provider.embedding_dimension,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": error,
        }

    return await _cached_probe("embedding", probe)


@router.get("/qdrant")
async def health_qdrant() -> Dict[str, Any]:
    start = time.monotonic()
    health = get_vector_store().health_check()
    return {**health, "latency_ms": round((time.monotonic() - start) * 1000, 1)}


@router.get("/neo4j")
async def health_neo4j() -> Dict[str, Any]:
    start = time.monotonic()
    health = get_graph_store().health_check()
    return {**health, "latency_ms": round((time.monotonic() - start) * 1000, 1)}


@router.get("/supabase")
async def health_supabase() -> Dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_url:
        return {"status": "not_configured"}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.supabase_url}/auth/v1/health")
        status = "ready" if resp.status_code < 500 else "degraded"
        return {"status": status, "http_status": resp.status_code, "latency_ms": round((time.monotonic() - start) * 1000, 1)}
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc)[:200], "latency_ms": round((time.monotonic() - start) * 1000, 1)}


@router.get("/redis")
async def health_redis() -> Dict[str, Any]:
    return await redis_cache.health_check()


@router.get("/providers")
async def health_providers() -> Dict[str, Any]:
    """Health for every configured provider (not just the active one), plus
    which one is currently active and the router/circuit-breaker state."""
    from app.llm.providers.gemini_provider import GeminiProvider
    from app.llm.providers.nvidia_provider import NvidiaProvider

    settings = get_settings()
    active = get_raw_provider()
    return {
        "active_provider": active.name,
        "gemini": GeminiProvider(settings).health_check(),
        "nvidia": NvidiaProvider(settings).health_check(),
        "router": get_llm_provider().health_check(),
    }
