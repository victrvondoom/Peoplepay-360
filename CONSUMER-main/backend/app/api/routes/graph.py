from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.models.domain import Domain

router = APIRouter()


@router.get("/patterns")
async def institution_patterns(domain: Domain, institution_name: str, _: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return await knowledge_graph.find_institution_patterns(domain, institution_name)


@router.get("/institution-radar")
async def institution_radar(limit: int = 25, _: CurrentUser = Depends(get_current_user)) -> list[dict]:
    """Aggregate, cross-citizen dispute volume per institution across every
    domain -- a public accountability view built entirely from real case
    data already in the graph (no separate tracking system), ranking which
    institutions accumulate the most real disputes. A pattern invisible in
    any single case (this institution has denied dozens of similar claims)
    becomes visible in aggregate."""
    return await knowledge_graph.get_institution_radar(limit)


@router.get("/similar-cases")
async def similar_cases(domain: Domain, institution_name: str, limit: int = 5, _: CurrentUser = Depends(get_current_user)) -> list[dict]:
    """Other real cases (across all citizens) logged against this domain +
    institution -- previously implemented on every GraphStore backend but
    never exposed via a route."""
    return await knowledge_graph.find_similar_cases(domain, institution_name, limit)


@router.get("/citizen/{user_id}/profile")
async def citizen_profile(user_id: str, current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Cross-domain traversal: every domain/institution/case linked to this
    citizen across all 8 domains (Enterprise Knowledge Graph)."""
    if current_user.role != "admin" and current_user.id != user_id:
        raise ProxyError("Cannot view another citizen's cross-domain profile", status_code=403, code="forbidden")
    return await knowledge_graph.get_citizen_profile(user_id)


# --------------------------------------------------------------------------
# Knowledge Graph page v2 (feature/knowledge-graph rebuild) -- Section 13 of
# the master spec. These reshape data that already exists (case records,
# agent_runs[].output.agent_trace, the existing patterns/similar-cases graph
# queries above) into the node/edge/trail contracts the new 3D page needs.
# No vector-store/RAG files touched; only case_repository (Postgres/local
# fallback) and the existing knowledge_graph facade above.
# --------------------------------------------------------------------------


def _domain_value(domain) -> str | None:
    return domain.value if hasattr(domain, "value") else domain


async def _load_case_or_synthetic(case_id: str, user_id: str) -> tuple[dict | None, list[dict], list[dict]]:
    """Mirrors reports.py's case_report fallback: a case created purely from
    an AI Assistant chat conversation (no formal "case" row) still has
    documents/appeals, so synthesize a minimal case shell for it rather than
    404ing."""
    case = await case_repository.get_case(case_id, user_id)
    appeals = [a for a in await case_repository.list_appeals(case_id) if a["user_id"] == user_id]
    documents = [d for d in await case_repository.list_documents(case_id) if d["user_id"] == user_id]

    if not case and (appeals or documents):
        domain = (appeals[0].get("domain") if appeals else None) or (documents[0].get("domain") if documents else None)
        case = {
            "id": case_id,
            "domain": domain,
            "title": appeals[0]["title"] if appeals else documents[0]["filename"],
            "institution_name": "Not specified",
            "summary": "Generated from an AI Assistant conversation, not a manually created case.",
            "status": "intake",
        }
    return case, appeals, documents


def _build_case_graph(case: dict, appeals: list[dict], documents: list[dict], latest_output: dict) -> dict:
    domain_value = _domain_value(case.get("domain")) or "unknown"
    nodes: list[dict] = [
        {
            "id": "case",
            "kind": "case",
            "label": case.get("title", "Untitled case"),
            "detail": {"title": case.get("title"), "summary": case.get("summary", ""), "status": case.get("status", "")},
        },
        {"id": "domain", "kind": "domain", "label": domain_value, "detail": {"domain": domain_value}},
    ]
    edges: list[dict] = [{"source": "case", "target": "domain"}]

    institution_name = case.get("institution_name")
    if institution_name and institution_name != "Not specified":
        nodes.append({"id": "institution", "kind": "institution", "label": institution_name, "detail": {"institution": institution_name}})
        edges.append({"source": "case", "target": "institution"})

    for doc in documents:
        # Documents are keyed by document_id, not id (see
        # case_repository.add_document) -- unlike cases/appeals which use id.
        node_id = f"document-{doc.get('document_id') or doc.get('id')}"
        nodes.append({
            "id": node_id,
            "kind": "document",
            "label": doc.get("filename", "Document"),
            "detail": {
                "filename": doc.get("filename"),
                "indexed": doc.get("indexed", False),
                "chunks_indexed": doc.get("chunks_indexed", 0),
                "text_extract": (doc.get("text_extract") or "")[:400],
            },
        })
        edges.append({"source": "case", "target": node_id})

    for appeal in appeals:
        node_id = f"appeal-{appeal['id']}"
        nodes.append({
            "id": node_id,
            "kind": "appeal",
            "label": appeal.get("title", "Appeal"),
            "detail": {
                "status": appeal.get("status"),
                "document_type": appeal.get("document_type"),
                "preview": (appeal.get("content") or "")[:400],
            },
        })
        edges.append({"source": "case", "target": node_id})

    citations_raw = latest_output.get("citations")
    # Defensive: some older/alternate-workflow agent_run outputs stored
    # citations as something other than a list (seen in real data as a
    # plain int) -- don't let one malformed run 500 the whole graph.
    citations = citations_raw if isinstance(citations_raw, list) else []
    seen: set[str] = set()
    reg_index = 0
    for citation in citations:
        text = str(citation).strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        node_id = f"regulation-{reg_index}"
        nodes.append({"id": node_id, "kind": "regulation", "label": text[:90], "detail": {"citation": text}})
        edges.append({"source": "case", "target": node_id})
        reg_index += 1
        if reg_index >= 8:
            break

    return {"case_id": case["id"], "domain": domain_value, "nodes": nodes, "edges": edges}


@router.get("/case/{case_id}/graph")
async def case_graph(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Full graph snapshot for Reasoning Trail mode (spec 13). Real case +
    appeals + documents + verified citations, reshaped into a generic
    nodes/edges contract the 3D scene renders directly -- no fabricated
    entities."""
    case, appeals, documents = await _load_case_or_synthetic(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")

    runs = await case_repository.list_agent_runs(case_id)
    latest_output = runs[-1].get("output", {}) if runs else {}
    return _build_case_graph(case, appeals, documents, latest_output)


def _classify_trace_token(token: str) -> str:
    """Best-effort mapping from a real agent_trace token (see grep of
    `agent_trace.append(...)` across backend/app/agents/**) to the graph
    entity kind that step concerns. Kept in sync conceptually with the
    frontend's agentTraceDetails.ts caption mapping, which owns the
    human-readable text -- this function only decides WHICH node to focus."""
    if (
        token.startswith("supervisor")
        or token in ("memory:loaded", "strategy:gemini", "review:gemini", "response:final")
        or token.startswith("response:")
        or token.startswith("final_report")
        or token.startswith("case_analysis")
    ):
        return "case"
    if (
        token.startswith("domain_router")
        or token.startswith("planner")
        or token.endswith("_orchestrator:start")
        or token.startswith("specialist")
    ):
        return "domain"
    if token.startswith("research") or token in ("retrieval:qdrant", "graph:neo4j") or token.startswith("web_search"):
        return "institution"
    if token == "evidence:gemini":
        return "document"
    if token.startswith("negotiation") or token.startswith("negotiator"):
        return "appeal"
    return "case"


@router.get("/case/{case_id}/reasoning-trail")
async def case_reasoning_trail(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Ordered traversal sequence for Reasoning Replay (spec 5.4 / 13).
    Reshapes the REAL agent_trace array already recorded by the LangGraph
    pipeline (case_workflow.py / case_analysis_workflow.py) into a per-step
    {index, token, node_id} sequence -- no new event-logging pipeline was
    built, because the ordered data already exists."""
    case, appeals, documents = await _load_case_or_synthetic(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")

    runs = await case_repository.list_agent_runs(case_id)
    latest_output = runs[-1].get("output", {}) if runs else {}
    trace_raw = latest_output.get("agent_trace")
    trace: list[str] = trace_raw if isinstance(trace_raw, list) else []

    document_ids = [f"document-{d.get('document_id') or d.get('id')}" for d in documents]
    appeal_ids = [f"appeal-{a['id']}" for a in appeals]
    doc_cursor = 0
    appeal_cursor = 0
    steps: list[dict] = []

    for index, token in enumerate(trace):
        kind = _classify_trace_token(token)
        if kind == "document":
            node_id = document_ids[min(doc_cursor, len(document_ids) - 1)] if document_ids else "case"
            doc_cursor += 1
        elif kind == "appeal":
            node_id = appeal_ids[min(appeal_cursor, len(appeal_ids) - 1)] if appeal_ids else "case"
            appeal_cursor += 1
        elif kind in ("domain", "institution"):
            node_id = kind
        else:
            node_id = "case"
        steps.append({"index": index, "token": token, "node_id": node_id})

    return {"case_id": case_id, "steps": steps}


@router.get("/institution-graph")
async def institution_graph(
    domain: Domain,
    institution_name: str,
    domain2: Domain | None = None,
    institution_name2: str | None = None,
    _: CurrentUser = Depends(get_current_user),
) -> dict:
    """Subgraph for Institution Intelligence mode (spec 6 / 13). Supports up
    to two simultaneous institution queries for Comparative Constellation;
    when both are present, also computes the real shared-entity overlap
    (matching pattern text or shared case id) server-side so the frontend
    doesn't need the raw untruncated data to draw the "shared" arcs."""
    queries: list[tuple[Domain, str]] = [(domain, institution_name)]
    if domain2 is not None and institution_name2:
        queries.append((domain2, institution_name2))

    institutions: list[dict] = []
    for index, (d, name) in enumerate(queries):
        patterns = await knowledge_graph.find_institution_patterns(d, name)
        similar_cases = await knowledge_graph.find_similar_cases(d, name, 5)
        institutions.append({
            "index": index,
            "domain": _domain_value(d),
            "institution_name": name,
            "patterns": patterns,
            "similar_cases": similar_cases,
        })

    shared: list[dict] = []
    if len(institutions) == 2:
        a, b = institutions
        for i0, p0 in enumerate(a["patterns"]):
            text0 = str(p0.get("pattern", "")).strip().lower()
            if not text0:
                continue
            for i1, p1 in enumerate(b["patterns"]):
                if text0 == str(p1.get("pattern", "")).strip().lower():
                    shared.append({"type": "pattern", "a_i": i0, "b_i": i1, "text": p0.get("pattern")})
        b_case_ids = {c.get("case_id") for c in b["similar_cases"]}
        for c in a["similar_cases"]:
            if c.get("case_id") in b_case_ids:
                shared.append({"type": "case", "case_id": c.get("case_id"), "title": c.get("title")})

    return {"institutions": institutions, "shared": shared}


@router.get("/user/knowledge-footprint")
async def user_knowledge_footprint(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Stat cards + Personal Knowledge Orrery data for My Knowledge
    Footprint mode (spec 7 / 13). Joins list_analyses_for_user (has real
    created_at + avg_confidence per case, already computed for "My
    Analyses") against the graph-derived citizen profile (has real
    institutions per domain) -- both pulled from existing repository/graph
    methods, no new storage."""
    analyses = await case_repository.list_analyses_for_user(user.id)
    profile = await knowledge_graph.get_citizen_profile(user.id)
    institutions_by_domain = {entry["domain"]: entry.get("institutions", []) for entry in profile.get("by_domain", [])}

    by_domain: dict[str, dict] = {}
    for a in analyses:
        domain_value = _domain_value(a.get("domain")) or "unknown"
        entry = by_domain.setdefault(domain_value, {"domain": domain_value, "cases": [], "institutions": institutions_by_domain.get(domain_value, [])})
        entry["cases"].append({
            "case_id": a["id"],
            "title": a.get("title", "Untitled case"),
            "created_at": a.get("created_at"),
            "avg_confidence": a.get("avg_confidence"),
        })

    domains_summary = sorted(
        (
            {"domain": domain_value, "case_count": len(entry["cases"]), "cases": entry["cases"], "institutions": entry["institutions"]}
            for domain_value, entry in by_domain.items()
        ),
        key=lambda d: d["case_count"],
        reverse=True,
    )

    confidences = [a["avg_confidence"] for a in analyses if a.get("avg_confidence") is not None]
    overall_confidence = round(sum(confidences) / len(confidences), 3) if confidences else None

    return {
        "user_id": user.id,
        "total_cases": len(analyses),
        "domains_active_in": [d["domain"] for d in domains_summary],
        "by_domain": domains_summary,
        "avg_confidence": overall_confidence,
        "most_active_domain": domains_summary[0]["domain"] if domains_summary else None,
    }
