"""Admin Panel backend: corpus/collection/graph/source health, ingestion
failures, logs, and per-user/API usage -- the data an enterprise dashboard
would render, exposed as plain JSON endpoints.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, require_admin
from app.core.logging import log_ring_buffer
from app.database.postgres.repositories import CaseRepository
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.llm.metrics import metrics
from app.models.domain import ACTIVE_DOMAINS
from app.rag.retrieval.collection_registry import get_collection_registry
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.reindex_service import KNOWLEDGE_ROOT, load_job

router = APIRouter()
_repo = CaseRepository()


def _load_manifest(domain_value: str) -> dict | None:
    manifest_path = KNOWLEDGE_ROOT / domain_value / f"{domain_value}_corpus_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@router.get("/documents")
async def documents_overview(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Per-domain document counts from each domain's corpus manifest."""
    domains = []
    for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
        manifest = _load_manifest(domain.value)
        domains.append({
            "domain": domain.value,
            "files_total": manifest.get("files_total") if manifest else None,
            "bytes_total": manifest.get("bytes_total") if manifest else None,
            "authority_counts": manifest.get("authority_counts") if manifest else None,
            "generated_at": manifest.get("generated_at") if manifest else None,
        })
    return {"domains": domains}


@router.get("/chunks")
async def chunks_overview(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Per-domain indexed chunk counts (live, from the active vector collection)."""
    return {
        "domains": [
            {"domain": domain.value, "chunks_indexed": qdrant_service.count(domain)}
            for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value)
        ]
    }


@router.get("/embeddings")
async def embeddings_overview(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Per-domain embedding dimension/provider/model + reindex-needed status."""
    return {
        "domains": [
            {"domain": domain.value, **qdrant_service.dimension_status(domain)}
            for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value)
        ]
    }


@router.get("/graph/stats")
async def graph_stats(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    from app.knowledge_graph.factory import get_graph_store
    store = get_graph_store()
    health = store.health_check()
    return {"health": health, "graph_latency_ms": {k: v for k, v in metrics.snapshot()["average_latency_ms"].items() if k.startswith("graph.")}}


@router.get("/domains/stats")
async def domains_stats(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """One combined row per domain: files, chunks, dimension, collection version."""
    registry = get_collection_registry()
    registry_snapshot = registry.snapshot().get("domains", {})
    domains = []
    for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
        manifest = _load_manifest(domain.value)
        status = qdrant_service.dimension_status(domain)
        entry = registry_snapshot.get(domain.value, {})
        domains.append({
            "domain": domain.value,
            "files_total": manifest.get("files_total") if manifest else None,
            "chunks_indexed": qdrant_service.count(domain),
            "dimension": status["current_dimension"],
            "needs_reindex": status["needs_reindex"],
            "active_version": entry.get("active_version"),
            "provider": status["provider"],
        })
    return {"domains": domains}


@router.get("/collections/health")
async def collections_health(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    return get_collection_registry().snapshot()


@router.get("/sources/health")
async def sources_health(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Per-domain source registry: how many entries, how many actually have
    content on disk (a rough proxy for scrape success vs. registered-but-failed)."""
    domains = []
    for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
        registry_path = KNOWLEDGE_ROOT / domain.value / f"{domain.value}_source_registry.json"
        if not registry_path.exists():
            domains.append({"domain": domain.value, "registry_found": False})
            continue
        try:
            entries = json.loads(registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            domains.append({"domain": domain.value, "registry_found": False})
            continue
        present = 0
        for entry in entries:
            candidate = KNOWLEDGE_ROOT / domain.value / entry.get("folder", "") / entry.get("slug", "")
            if any(candidate.with_suffix(ext).exists() for ext in (".txt", ".pdf", ".html")):
                present += 1
        domains.append({
            "domain": domain.value,
            "registry_found": True,
            "registered_sources": len(entries),
            "sources_with_content": present,
            "sources_failed": len(entries) - present,
        })
    return {"domains": domains}


@router.get("/ingestion/failed")
async def failed_ingestion(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Per-domain oversized/skipped/failed files from the last reindex job."""
    domains = []
    for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
        job = load_job(domain)
        if not job:
            continue
        domains.append({
            "domain": domain.value,
            "status": job.status,
            "failed_chunks": job.failed_chunks,
            "skipped_oversized_files": job.skipped_oversized_files,
            "error": job.error,
        })
    return {"domains": domains}


@router.get("/logs")
async def recent_logs(level: str | None = None, limit: int = 200, _: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    return {"logs": log_ring_buffer.snapshot(level=level, limit=limit)}


@router.get("/users")
async def users_overview(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Distinct users seen in the local case store, with case counts --
    there's no separate user table (auth is delegated to Supabase), so this
    is derived from actual case activity rather than fabricated."""
    cases = _repo.local.read("cases")
    by_user: dict[str, int] = {}
    for case in cases:
        user_id = case.get("user_id")
        if user_id:
            by_user[user_id] = by_user.get(user_id, 0) + 1
    return {
        "total_distinct_users": len(by_user),
        "users": [{"user_id": uid, "case_count": count} for uid, count in sorted(by_user.items(), key=lambda kv: kv[1], reverse=True)],
    }


@router.get("/evaluation")
async def evaluation_benchmark(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """Fast evaluation (no LLM calls): domain-classification accuracy,
    specialist-routing accuracy, and retrieval hit-rate/latency over every
    synthetic case per domain. See app.services.evaluation_service for the
    (deliberately LLM-call-bounded) deep-eval variant, run via the CLI
    script rather than an open GET endpoint."""
    from app.models.domain import ACTIVE_DOMAINS
    from app.services.evaluation_service import evaluate_domain_fast

    results = []
    for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
        result = await evaluate_domain_fast(domain)
        if result:
            results.append(result)
    return {"domains": results}


@router.get("/usage")
async def api_usage(_: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """API call volume/error counts per route, from the request middleware's
    live counters (see app.middleware.request_context)."""
    snapshot = metrics.snapshot()
    counters = snapshot["counters"]
    latencies = snapshot["average_latency_ms"]
    api_latency = {k: v for k, v in latencies.items() if k.startswith("api.")}
    api_errors = {k: v for k, v in counters.items() if k.startswith("api_errors.")}
    return {
        "total_requests": counters.get("api_requests_total", 0),
        "latency_by_route_ms": api_latency,
        "errors_by_route": api_errors,
    }
