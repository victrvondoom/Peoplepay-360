"""Global Retrieval Engine — searches multiple domains' Qdrant/jsonl
collections in parallel and merges the results into one ranked list, instead
of the single-domain search every domain specialist currently does alone.

Ranking uses the Evidence Scoring Engine (similarity + authority + legal
weight + freshness) rather than raw vector similarity alone.
"""
from __future__ import annotations

import asyncio

from app.llm.service import llm_service
from app.models.domain import ACTIVE_DOMAINS, Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.evidence_scoring import score_evidence_batch


async def _search_one_domain(domain: Domain, query: str, top_k: int, query_vector: list[float]) -> list[dict]:
    try:
        hits = await qdrant_service.search(domain, query, limit=top_k, query_vector=query_vector)
    except Exception:
        return []
    return score_evidence_batch(domain, hits)


async def global_search(
    query: str,
    domains: list[Domain] | None = None,
    top_k_per_domain: int = 5,
    top_k_overall: int = 15,
) -> dict:
    """Search across `domains` (default: every active domain) and return a
    single evidence-ranked list plus a per-domain breakdown.

    Runs one search per domain concurrently — cost is bounded by the slowest
    single domain's Qdrant/jsonl query, not the sum of all of them. The
    query text is identical across every domain, so it's embedded exactly
    once here and the vector is reused for all of them, rather than each
    domain paying for its own redundant embedding call.
    """
    target_domains = domains or sorted(ACTIVE_DOMAINS, key=lambda d: d.value)
    query_vector = await llm_service.embed_query(query)
    results_per_domain = await asyncio.gather(
        *(_search_one_domain(domain, query, top_k_per_domain, query_vector) for domain in target_domains)
    )

    merged: list[dict] = []
    per_domain: dict[str, list[dict]] = {}
    for domain, hits in zip(target_domains, results_per_domain):
        per_domain[domain.value] = hits
        merged.extend(hits)

    merged.sort(key=lambda item: item["evidence_scores"]["overall_evidence_score"], reverse=True)

    return {
        "query": query,
        "domains_searched": [d.value for d in target_domains],
        "results": merged[:top_k_overall],
        "results_by_domain": per_domain,
        "total_hits": len(merged),
    }
