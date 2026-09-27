"""Citation Engine — turns scored evidence hits into structured, clickable
citations: title, official URL, publication date (when known), section,
the retrieved chunk itself, and a confidence score.
"""
from __future__ import annotations

from app.models.domain import Domain
from app.services.evidence_scoring import score_evidence_batch

MAX_SNIPPET_CHARS = 400


def build_citation(scored_hit: dict) -> dict:
    metadata = scored_hit.get("metadata", {})
    scores = scored_hit.get("evidence_scores", {})
    text = scored_hit.get("text", "")
    snippet = text[:MAX_SNIPPET_CHARS] + ("…" if len(text) > MAX_SNIPPET_CHARS else "")

    return {
        "title": metadata.get("title") or metadata.get("document_id") or "Untitled source",
        "authority": metadata.get("authority", "Unknown"),
        "url": metadata.get("source_url"),
        "publication_date": metadata.get("published_date") or metadata.get("publication_date"),
        "section": metadata.get("category"),
        "domain": scored_hit.get("domain"),
        "retrieved_chunk": snippet,
        "confidence": scores.get("confidence", scores.get("overall_evidence_score", 0.5)),
        "evidence_scores": scores,
    }


def build_citations(domain: Domain, hits: list[dict], max_citations: int = 8) -> list[dict]:
    """Score, rank, and de-duplicate (by URL/title) retrieval hits into a
    citation list ready to attach to a final answer."""
    scored = score_evidence_batch(domain, hits)
    citations: list[dict] = []
    seen_keys: set[str] = set()
    for hit in scored:
        citation = build_citation(hit)
        dedupe_key = citation["url"] or citation["title"]
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        citations.append(citation)
        if len(citations) >= max_citations:
            break
    return citations


def format_citations_for_prompt(citations: list[dict]) -> str:
    """Render citations as numbered references an LLM can cite inline (e.g. [1])
    and a human can later render as clickable links from the same list."""
    lines = []
    for index, citation in enumerate(citations, start=1):
        url_part = f" — {citation['url']}" if citation.get("url") else ""
        lines.append(f"[{index}] {citation['title']} ({citation['authority']}){url_part}")
    return "\n".join(lines)
