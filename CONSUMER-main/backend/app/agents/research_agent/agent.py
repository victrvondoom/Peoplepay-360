"""Research Agent — searches Qdrant, Neo4j, and Web to answer:

- Which clauses apply?
- Which exclusions apply?
- Which waiting period applies?
- Which regulations apply?
"""

from __future__ import annotations

from app.agents.json_parser import parse_agent_json, unwrap_nested_json_summary
from app.agents.state import AgentState, ResearchOutput
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.llm.service import llm_service
from app.prompts.domain_profiles import get_profile
from app.prompts.health_insurance_agents import research_prompt
from app.rag.retrieval.qdrant_service import qdrant_service
from app.services.citation_verification import verify_claims
from app.services.web_search import web_search_service

RESEARCH_FALLBACK_FIELDS: dict = {
    "applicable_clauses": [],
    "possible_exclusions": [],
    "waiting_periods": [],
    "regulations": [],
    "confidence": 0.0,
}


def rank_hits(hits: list[dict]) -> list[dict]:
    """Rank vector search hits by score with authority boost."""
    for hit in hits:
        score = float(hit.get("score", 0))
        meta = hit.get("metadata", {})
        # Boost IRDAI, RBI, NPCI and regulatory sources
        authority = (meta.get("authority") or meta.get("category") or "").lower()
        if any(keyword in authority for keyword in ("irdai", "rbi", "npci", "regulation", "circular", "guideline", "ombudsman")):
            score += 0.5
        # Boost insurer/bank-specific documents
        if meta.get("insurer_name") or meta.get("bank"):
            score += 0.05
        hit["_rank_score"] = min(score, 1.0)
    return sorted(hits, key=lambda h: h.get("_rank_score", 0), reverse=True)


async def run_research_agent(state: AgentState) -> AgentState:
    """Execute the research agent: search Qdrant + Neo4j + Web, then synthesize via Gemini."""
    domain = state["domain"]
    # `.get(key, "")` only falls back to "" when the key is *missing* -- a
    # caller that explicitly sets institution_name=None (a legitimate case:
    # a general-purpose query with no specific institution) still gets None
    # through here, which then crashes cache-key hashing (str-only) downstream.
    institution = state.get("institution_name") or ""
    case_summary = state.get("case_summary", "")
    profile = get_profile(domain)
    # Previously hardcoded to health-insurance terms ("IRDAI health insurance
    # regulations", "medical necessity pre-authorization") regardless of
    # domain -- every other domain's vector search was polluted with
    # irrelevant insurance jargon. Now pulls the same domain profile the
    # prompts use, so a banking/airlines/housing/etc. case searches for its
    # own actually-relevant terms.
    combined_query = f"{case_summary} {institution} " + " ".join(profile.research_questions)

    # --- 1. Vector search (Qdrant) ---
    all_hits: list[dict] = []
    seen: set[str] = set()
    for query in [combined_query, f"{institution} {profile.counterparty} rules regulations terms"]:
        hits = await qdrant_service.search(domain, query, limit=6)
        for hit in hits:
            hit_id = str(hit.get("id"))
            if hit_id not in seen:
                seen.add(hit_id)
                all_hits.append(hit)

    # --- 2. Knowledge Graph (Neo4j) ---
    patterns = await knowledge_graph.find_institution_patterns(domain, institution)
    graph_lines = [p.get("pattern", "") for p in patterns if p.get("pattern")]
    state["graph_context"] = "\n".join(graph_lines)
    # Keep the structured list too (not just the flattened string) so callers
    # that want real per-pattern confidence scores -- e.g. the New Analysis
    # results view's Knowledge Graph section -- don't have to re-query.
    state["graph_patterns"] = patterns

    # --- 3. Web Search ---
    # Previously only banking got a domain-appropriate query -- every other
    # domain (airlines, telecom, ecommerce, government, housing, healthcare)
    # searched the web for "health insurance claim denial IRDAI appeal"
    # regardless of what the case was actually about.
    if profile.is_dispute:
        web_query = f"{institution} {profile.counterparty} dispute {profile.regulator} complaint {case_summary[:200]}"
    else:
        web_query = f"{case_summary[:200]} symptoms causes treatment WHO guidance"
    web_results = await web_search_service.search(web_query, max_results=3)

    state["web_search_results"] = web_results
    web_context = ""
    if web_results:
        web_context = "\n\n".join(
            f"Web: {r.get('title', '')}\n{r.get('url', '')}\n{r.get('snippet', '')}" for r in web_results
        )

    # --- 4. Rank and format context ---
    ranked = rank_hits(all_hits)[:10]
    state["retrieved_context"] = "\n\n".join(
        f"Source: {hit.get('metadata', {}).get('title') or hit.get('metadata', {}).get('filename') or hit['id']}\n"
        f"Authority: {hit.get('metadata', {}).get('authority') or hit.get('metadata', {}).get('insurer_name', 'unknown')}\n"
        f"Category: {hit.get('metadata', {}).get('category', 'unknown')}\n"
        f"Citation: {hit.get('metadata', {}).get('final_url') or hit.get('metadata', {}).get('source_path') or hit['id']}\n"
        f"Text: {hit.get('text', '')[:1500]}"
        for hit in ranked
    )
    if web_context:
        state["retrieved_context"] = f"{state.get('retrieved_context', '')}\n\n{web_context}".strip()

    # --- 5. Gemini synthesis ---
    prompt = research_prompt(
        domain,
        case_summary,
        state.get("retrieved_context", ""),
        state.get("graph_context", ""),
    )
    raw = await llm_service.generate(prompt, temperature=0.15, purpose="reasoning")

    # --- 6. Parse structured output ---
    parsed = parse_agent_json(raw, RESEARCH_FALLBACK_FIELDS)
    regulations = parsed.get("regulations", [])
    # Deterministic check, not another LLM call: does each cited regulation
    # actually appear in the text this agent was given? A hallucinated
    # citation otherwise sails through with no ground-truth check at all.
    _, unverified_regulations = verify_claims(regulations, state.get("retrieved_context", ""))
    research_output: ResearchOutput = {
        "applicable_clauses": parsed.get("applicable_clauses", []),
        "possible_exclusions": parsed.get("possible_exclusions", []),
        "waiting_periods": parsed.get("waiting_periods", []),
        "regulations": regulations,
        "unverified_regulations": unverified_regulations,
        "summary": unwrap_nested_json_summary(parsed.get("summary", raw[:2000])),
        "confidence": float(parsed.get("confidence", 0.5)),
    }
    state["research_output"] = research_output
    state["research_summary"] = research_output["summary"]
    state["citations"] = [
        hit.get("metadata", {}).get("final_url") or hit.get("metadata", {}).get("source_path") or str(hit.get("id"))
        for hit in ranked
    ]
    from app.services.citation_engine import build_citations
    state["structured_citations"] = build_citations(domain, ranked)
    state["llm_call_count"] = int(state.get("llm_call_count", 0)) + 1
    state.setdefault("agent_trace", []).append("research:qdrant+graph+web+gemini")
    return state
