"""Admin endpoints for LLM/embedding operations: reindex status + control,
runtime model overrides ("hot switching"), and call metrics.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.auth.dependencies import CurrentUser, require_admin, require_admin_or_api_key
from app.llm.metrics import metrics
from app.llm.runtime_overrides import runtime_overrides
from app.llm.service import get_llm_provider, get_raw_provider
from app.models.domain import ACTIVE_DOMAINS, Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.audit_log import read_audit_log, record_audit_event
from app.services.reindex_service import ReindexJob, load_job, run_reindex

router = APIRouter()


@router.get("/reindex-status")
async def reindex_status(_: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    """Per-domain embedding status: current vs target dimension, chunk
    count, in-flight job progress (if any), and last-indexed time."""
    domains = []
    for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
        status = qdrant_service.dimension_status(domain)
        job = load_job(domain)
        domains.append({
            "domain": domain.value,
            "current_dimension": status["current_dimension"],
            "target_dimension": status["target_dimension"],
            "needs_reindex": status["needs_reindex"],
            "provider": status["provider"],
            "embedding_model": status["embedding_model"],
            "chunks": qdrant_service.count(domain),
            "progress_percent": job.progress_percent if job else (0.0 if status["needs_reindex"] else 100.0),
            "job_status": job.status if job else ("needs_reindex" if status["needs_reindex"] else "up_to_date"),
            "last_indexed": status["last_indexed"],
        })
    return {"domains": domains}


@router.post("/reindex/{domain}")
async def trigger_reindex(
    domain: Domain, background_tasks: BackgroundTasks, user: CurrentUser = Depends(require_admin_or_api_key)
) -> Dict[str, Any]:
    if domain not in ACTIVE_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Domain '{domain.value}' is not active")

    existing = load_job(domain)
    if existing and existing.status == "running":
        raise HTTPException(status_code=409, detail=f"Reindex already running for '{domain.value}'")

    resuming = bool(existing and existing.status in {"failed", "failed_verification", "verifying"})
    record_audit_event(user.id, "trigger_reindex", {"domain": domain.value, "resumed": resuming})
    background_tasks.add_task(run_reindex, domain)
    return {
        "message": f"Reindex {'resumed' if resuming else 'started'} for '{domain.value}'",
        "domain": domain.value,
        "resumed": resuming,
    }


@router.get("/reindex/{domain}/status")
async def reindex_job_status(domain: Domain, _: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    job = load_job(domain)
    if job is None:
        return {"domain": domain.value, "status": "never_run"}
    return job.to_dict()


@router.get("/migration-report")
async def migration_report(_: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    from app.rag.retrieval.collection_registry import get_collection_registry

    registry = get_collection_registry()
    domains_report = []
    warnings: list[str] = []
    failures: list[str] = []
    total_chunks_migrated = 0
    collections_migrated = 0

    for domain in sorted(ACTIVE_DOMAINS, key=lambda d: d.value):
        status = qdrant_service.dimension_status(domain)
        job = load_job(domain)
        entry = registry.snapshot().get("domains", {}).get(domain.value, {})
        versions = entry.get("versions", {})
        old_versions = [v for label, v in versions.items() if label != entry.get("active_version")]
        old_dimension = old_versions[0]["dimension"] if old_versions else None

        if job and job.status == "completed":
            collections_migrated += 1
            total_chunks_migrated += job.completed_chunks
        if job and job.status == "failed_verification":
            failures.append(f"{domain.value}: verification failed ({job.error})")
        if status["needs_reindex"] and (not job or job.status != "running"):
            warnings.append(f"{domain.value}: needs reindex (current={status['current_dimension']}, target={status['target_dimension']})")

        domains_report.append({
            "domain": domain.value,
            "pre_migration_dimension": old_dimension,
            "current_dimension": status["current_dimension"],
            "target_dimension": status["target_dimension"],
            "needs_reindex": status["needs_reindex"],
            "chunks": qdrant_service.count(domain),
            "job_status": job.status if job else "never_run",
        })

    return {
        "provider": get_raw_provider().name,
        "collections_migrated": collections_migrated,
        "chunks_migrated": total_chunks_migrated,
        "domains": domains_report,
        "failures": failures,
        "warnings": warnings,
        "final_health_status": get_llm_provider().health_check(),
    }


@router.get("/metrics")
async def get_metrics(_: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    return metrics.snapshot()


@router.get("/observability")
async def observability_dashboard(_: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    """Latency/error/retry stats grouped by category (agent, LLM, embedding,
    vector search, graph, API), built from the same underlying MetricsStore
    /metrics exposes flat -- this is a friendlier shape for a dashboard."""
    snapshot = metrics.snapshot()
    latencies = snapshot["average_latency_ms"]
    counters = snapshot["counters"]

    def _match(prefix: str) -> dict:
        return {k: v for k, v in latencies.items() if k.startswith(prefix)}

    total_requests = counters.get("api_requests_total", 0)
    total_errors = sum(v for k, v in counters.items() if k.startswith("api_errors."))
    total_fallbacks = counters.get("fallback_count", 0)
    total_llm_unavailable = counters.get("llm_unavailable_count", 0)

    provider = get_raw_provider()
    circuit_state = provider.health_check().get("circuit_breaker") if hasattr(provider, "health_check") else None

    return {
        "agent_latency_ms": _match("router."),
        "llm_latency_ms": {k: v for k, v in latencies.items() if k.startswith("router.") or k.startswith("nvidia.") or k.startswith("gemini.")},
        "embedding_latency_ms": _match("embedding."),
        "vector_search_latency_ms": _match("vector_search."),
        "graph_latency_ms": _match("graph."),
        "api_latency_ms": _match("api."),
        "success_rate": {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "success_rate_percent": round(100 * (1 - total_errors / total_requests), 2) if total_requests else None,
        },
        "retry_and_fallback_counts": {
            "model_router_fallbacks": total_fallbacks,
            "llm_unavailable": total_llm_unavailable,
            "circuit_breaker_open_skips": counters.get("circuit_breaker_open_skips", 0,),
        },
        "circuit_breaker": circuit_state,
        "raw_counters": counters,
    }


@router.get("/llm/model")
async def get_model_overrides(_: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    provider = get_raw_provider()
    return {
        "provider": provider.name,
        "defaults": {
            purpose: provider.model_for(purpose)
            for purpose in ("reasoning", "router", "planner", "response", "summarization", "ocr", "kg_extraction")
        },
        "overrides": runtime_overrides.snapshot(),
    }


@router.post("/llm/model")
async def set_model_override(payload: Dict[str, str], user: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    """Hot-switch a purpose's model without restarting the process.

    Body: {"provider": "nvidia", "purpose": "reasoning", "model": "meta/llama-3.3-70b-instruct"}
    `purpose` may be omitted to override every purpose for that provider.
    """
    provider = payload.get("provider") or get_raw_provider().name
    model = payload.get("model")
    if not model:
        raise HTTPException(status_code=400, detail="'model' is required")
    purpose = payload.get("purpose")
    runtime_overrides.set_model(provider, purpose, model)
    record_audit_event(user.id, "set_model_override", {"provider": provider, "purpose": purpose, "model": model})
    return {"message": "Model override applied", "provider": provider, "purpose": purpose or "*", "model": model}


@router.delete("/llm/model")
async def clear_model_override(provider: str | None = None, purpose: str | None = None, user: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    resolved_provider = provider or get_raw_provider().name
    runtime_overrides.clear(resolved_provider, purpose)
    record_audit_event(user.id, "clear_model_override", {"provider": resolved_provider, "purpose": purpose})
    return {"message": "Model override cleared", "provider": resolved_provider, "purpose": purpose or "*"}


@router.get("/audit-log")
async def audit_log(limit: int = 200, _: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    return {"entries": read_audit_log(limit)}
