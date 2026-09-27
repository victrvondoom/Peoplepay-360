"""Evidence Scoring Engine — scores every retrieved chunk on authority,
freshness, similarity, and legal weight, then blends them into one overall
score so retrieval results can be ranked by more than raw vector similarity.

Chunks indexed after the reindex_service.py metadata enrichment carry
authority/category/source_url directly in their payload; older chunks fall
back to a sidecar-file lookup by source_path (see app.rag.source_metadata).
"""
from __future__ import annotations

from app.models.domain import Domain
from app.rag.source_metadata import load_source_metadata

# Authority tiers: reflects how much weight a domain expert would give a
# source, independent of how well it happens to match a query semantically.
# Tier 1 = the actual regulator/statute/primary agency for that domain.
# Tier 2 = an official government body adjacent to the primary regulator.
# Tier 3 = general reference/background (Wikipedia, general education notes).
_TIER_1_AUTHORITIES = {
    "rbi", "dgca", "moca", "uidai", "irdai", "trai", "who", "cdsco", "icmr",
    "mohfw", "goi", "govt of india", "ncdrc", "rera", "national health authority",
}
_TIER_2_AUTHORITIES = {
    "darpg", "mea", "income tax dept", "protean (nsdl)", "parivahan", "rti online",
    "tn rera", "maharera", "karnataka rera", "kerala rera", "up rera",
    "tn registration dept", "karnataka land records", "dept of land resources",
    "nha", "national health mission", "aiims", "cdc", "nih", "medlineplus",
    "general public health education",
}
_LEGAL_WEIGHT_CATEGORIES = {
    "act", "regulations", "kyc", "cards", "loans", "deposits", "consumer_protection",
    "passenger_facilities", "refunds", "accessibility", "digital_security",
}


def _authority_score(authority: str) -> float:
    key = (authority or "").strip().lower()
    if not key:
        return 0.5
    if key in _TIER_1_AUTHORITIES or any(t in key for t in _TIER_1_AUTHORITIES):
        return 1.0
    if key == "wikipedia":
        return 0.55
    if key in _TIER_2_AUTHORITIES or any(t in key for t in _TIER_2_AUTHORITIES):
        return 0.8
    return 0.6


def _legal_weight(category: str, doc_type: str) -> float:
    key = (category or "").strip().lower()
    if key in _LEGAL_WEIGHT_CATEGORIES or "act" in key or "regulation" in key or "master_direction" in key:
        return 1.0
    if key in {"faq", "guide", "grievance_portal", "complaints"}:
        return 0.7
    if key in {"overview", "law_overview"}:
        return 0.5
    return 0.6


def _freshness_score(metadata: dict) -> float:
    # Most sources here don't carry an explicit publication date (scraped
    # government/regulator pages rarely expose one cleanly) — default to a
    # neutral score rather than penalize undated-but-authoritative content.
    for key in ("published_date", "publication_date", "last_updated"):
        if metadata.get(key):
            return 0.75
    return 0.6


def enrich_metadata(domain: Domain, metadata: dict) -> dict:
    """Fill in authority/category/source_url from the sidecar file when the
    chunk's own payload doesn't already carry them (pre-enrichment data)."""
    if metadata.get("authority") or metadata.get("category"):
        return metadata
    sidecar = load_source_metadata(domain, metadata.get("source_path", "") or metadata.get("document_id", ""))
    if not sidecar:
        return metadata
    merged = dict(sidecar)
    merged.update(metadata)
    return merged


def score_evidence(domain: Domain, hit: dict) -> dict:
    """Attach authority_score/freshness_score/legal_weight/confidence/
    overall_evidence_score to a single retrieval hit (from qdrant_service.search)."""
    metadata = enrich_metadata(domain, dict(hit.get("metadata", {})))
    similarity_score = max(0.0, min(1.0, float(hit.get("score", 0.0))))
    authority_score = _authority_score(metadata.get("authority", ""))
    legal_weight = _legal_weight(metadata.get("category", ""), metadata.get("type", ""))
    freshness_score = _freshness_score(metadata)

    # Similarity gates relevance; authority/legal-weight/freshness modify it by
    # at most +/-40% rather than competing with it additively. Without this, a
    # barely-relevant chunk from a Tier-1 authority (e.g. a UIDAI passage for
    # an airlines query) could outrank a genuinely relevant chunk from a
    # lower-tier source, which is backwards for cross-domain search.
    authority_composite = 0.60 * authority_score + 0.25 * legal_weight + 0.15 * freshness_score
    overall = similarity_score * (0.6 + 0.4 * authority_composite)
    # Confidence discounts the overall score when a chunk has no identifiable
    # source at all (synthetic/offline-fallback content), since we can't back
    # it with a citation.
    confidence = overall if metadata.get("authority") or metadata.get("source_url") else overall * 0.6

    scored = dict(hit)
    scored["metadata"] = metadata
    scored["domain"] = domain.value
    scored["evidence_scores"] = {
        "similarity_score": round(similarity_score, 3),
        "authority_score": round(authority_score, 3),
        "legal_weight": round(legal_weight, 3),
        "freshness_score": round(freshness_score, 3),
        "confidence": round(confidence, 3),
        "overall_evidence_score": round(overall, 3),
    }
    return scored


def score_evidence_batch(domain: Domain, hits: list[dict]) -> list[dict]:
    scored = [score_evidence(domain, hit) for hit in hits]
    scored.sort(key=lambda item: item["evidence_scores"]["overall_evidence_score"], reverse=True)
    return scored
