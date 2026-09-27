"""Multi-domain case entry point: classify a raw query against every active
domain (Domain Router), run the full case workflow once per candidate
domain concurrently, and merge the results into one combined report --
implements the prompt's example directly: "My flight was cancelled and my
travel insurance rejected the claim" -> run Airlines AND Health Insurance,
merge results, instead of forcing the caller to pick one domain upfront.
"""
from __future__ import annotations

import asyncio

from app.agents.orchestrator.case_workflow import case_workflow
from app.agents.role_agents.domain_router import classify_domains_multilingual
from app.services.case_context import build_evidence_bundle

# NegotiationOutput's fields (app/agents/state.py) mapped to a human title
# used both for the saved Appeal's title and the frontend's document-type
# labels -- kept in one place so the two stay in sync.
DOCUMENT_TYPE_TITLES = {
    "appeal_letter": "Appeal Letter",
    "complaint_email": "Complaint Email",
    "escalation_note": "Escalation Note",
    "consumer_complaint": "Consumer Complaint",
}


async def _save_appeals_for_domain(user_id: str, case_id: str, domain_value: str, query: str, state: dict) -> list[dict]:
    negotiation_output = state.get("negotiation_output") or {}
    if not isinstance(negotiation_output, dict):
        return []
    from app.database.postgres.repositories import case_repository

    saved = []
    query_snippet = query[:80] + ("..." if len(query) > 80 else "")
    for doc_type, title_prefix in DOCUMENT_TYPE_TITLES.items():
        content = negotiation_output.get(doc_type)
        if not content or not isinstance(content, str) or not content.strip():
            continue
        appeal = await case_repository.add_appeal(
            case_id, user_id, f"{title_prefix}: {query_snippet}", content,
            document_type=doc_type, domain=domain_value,
        )
        saved.append(appeal)
    return saved


_NOT_SPECIFIED_REPLIES = {"not specified", "none", "n/a", "na", "unknown", "unspecified", ""}


async def _extract_institution_name(case_summary: str) -> str:
    """Nearly every case created through the New Analysis / AI Assistant
    flow (i.e. almost all cases outside the older health_insurance-only
    intake form) was landing with institution_name literally set to "Not
    specified", because the caller never supplies one and nothing ever
    tried to read it out of the free-text summary -- even though the summary
    usually names the counterparty directly ("Zenwave Mobile Bank...", "my
    builder...", "Air India..."). That silently broke Institution
    Intelligence for 7 of 8 domains: there was no real institution name on
    the case to match patterns/similar-cases against. One cheap, short LLM
    call here (not a new agent, not a new pipeline stage) fixes that for
    every new case going forward."""
    if not case_summary or not case_summary.strip():
        return "Not specified"
    from app.llm.service import llm_service

    prompt = (
        "Extract ONLY the name of the specific company, bank, airline, insurer, builder, "
        "or other institution/counterparty named in this consumer complaint. Reply with "
        "just the name, nothing else -- no explanation, no punctuation beyond what's in the "
        "name itself. If no specific institution is named (e.g. it only says \"my bank\" or "
        "\"the airline\" with no proper name), reply with exactly: Not specified\n\n"
        f"Complaint text:\n{case_summary[:1500]}"
    )
    try:
        raw = await llm_service.generate(prompt, temperature=0.0, purpose="reasoning")
    except Exception:
        return "Not specified"
    name = raw.strip().strip('"').strip("'").split("\n")[0].strip()
    if not name or name.lower() in _NOT_SPECIFIED_REPLIES or len(name) > 80:
        return "Not specified"
    return name


async def _create_analysis_case(user_id: str, case_id: str, primary_domain, query: str, institution_name: str) -> None:
    """Every multi-domain query becomes a real, listable Case -- previously
    only appeals/documents persisted anything, so "My Analyses" would be
    empty for the primary interaction path (the AI Assistant) even though
    real multi-agent analysis work was happening on every query."""
    if not user_id:
        return
    from app.database.postgres.repositories import case_repository
    from app.schemas.cases import CaseCreate, CaseStatus

    if not institution_name:
        institution_name = await _extract_institution_name(query)

    query_snippet = query[:120] + ("..." if len(query) > 120 else "")
    await case_repository.create_case(
        user_id,
        CaseCreate(
            domain=primary_domain,
            title=query_snippet or "Untitled analysis",
            institution_name=institution_name or "Not specified",
            summary=query or query_snippet,
        ),
        case_id=case_id,
    )
    await case_repository.update_case_status(case_id, CaseStatus.ANALYZING)


async def _record_analysis_runs(user_id: str, case_id: str, per_domain_results: list[dict], query: str) -> None:
    if not user_id:
        return
    from app.database.postgres.repositories import case_repository
    from app.schemas.cases import CaseStatus

    any_succeeded = False
    for entry in per_domain_results:
        state = entry["state"]
        final = state.get("final_report") or state.get("final_answer")
        succeeded = bool(final)
        any_succeeded = any_succeeded or succeeded
        await case_repository.add_agent_run(
            case_id,
            f"multi_domain:{entry['domain']}",
            status="completed" if succeeded else "failed",
            input_payload={"query": query, "domain": entry["domain"]},
            # Previously saved only {domain, confidence, route, citation
            # COUNT} -- /reports/case/{case_id} (the "My Analyses" detail
            # view) reads agent_runs[-1].output.strategy/research_summary/
            # evidence_summary/appeal_draft/final_report as flat keys, the
            # shape case_analysis_workflow.py's single-domain pipeline
            # produces. The multi-domain pipeline (the one actually used by
            # both the New Analysis and AI Assistant pages) discarded all of
            # that real, already-generated content before it was ever
            # persisted, so a case analyzed through either of those surfaces
            # showed "Strategy not yet generated" etc. on reload even though
            # the analysis had genuinely run and produced real content --
            # confirmed live against a real saved case.
            output_payload={
                "domain": entry["domain"],
                "confidence": entry["confidence"],
                "route": state.get("route"),
                "research_summary": state.get("research_summary", ""),
                "evidence_summary": state.get("evidence_summary", ""),
                "strategy": state.get("strategy", ""),
                "appeal_draft": state.get("appeal_draft", ""),
                "final_report": final or "",
                "review_notes": state.get("review_notes", []),
                "citations": state.get("citations", []),
                "agent_trace": state.get("agent_trace", []),
                "llm_call_count": state.get("llm_call_count", 0),
            },
        )
    await case_repository.update_case_status(
        case_id, CaseStatus.REVIEW_REQUIRED if any_succeeded else CaseStatus.ANALYZING
    )


async def _fetch_evidence_documents(user_id: str, document_ids: list[str]) -> list[dict]:
    """Fetch the exact documents the caller uploaded for this run (by id,
    scoped to user_id) -- not every historical document in that domain's
    vault, which would let unrelated old uploads bleed into every future
    analysis for the same domain."""
    if not user_id or not document_ids:
        return []
    from app.database.postgres.repositories import case_repository
    return await case_repository.get_documents_by_ids(document_ids, user_id)


async def run_multi_domain_case(base_state: dict, save_appeals: bool = False) -> dict:
    query = base_state.get("case_summary", "")
    user_id = base_state.get("user_id", "")
    document_ids = base_state.get("document_ids") or []
    documents = await _fetch_evidence_documents(user_id, document_ids)
    evidence_bundle = build_evidence_bundle(documents)

    # Uploaded evidence can carry its own domain signal (e.g. a RERA
    # possession notice uploaded alongside a vague "my builder is delaying
    # things" query) -- classify against the query PLUS a snippet of every
    # uploaded document's real extracted text, not the query text alone.
    classification_text = query
    for doc in documents:
        extract = (doc.get("text_extract") or "")[:2000]
        if extract:
            classification_text = f"{classification_text}\n{extract}"
    candidates = await classify_domains_multilingual(classification_text)
    base_case_id = base_state.get("case_id", "case")

    await _create_analysis_case(user_id, base_case_id, candidates[0]["domain"], query, base_state.get("institution_name", ""))

    async def run_for_candidate(candidate: dict) -> dict:
        domain = candidate["domain"]
        state = dict(base_state)
        state["domain"] = domain
        case_id = f"{base_case_id}-{domain.value}"
        state["case_id"] = case_id
        state["base_case_id"] = base_case_id
        state["evidence_bundle"] = evidence_bundle
        state["documents"] = documents
        result = await case_workflow.run(state)
        # base_case_id, not the per-domain-suffixed case_id above -- appeals
        # must be saved under the real case's id (the one actually shown on
        # the case report / Appeals page) or they silently never appear
        # there even though they were genuinely generated. This was a real,
        # confirmed bug: live-tested a case with generate_appeals=true,
        # all 4 appeal documents were created correctly but every one of
        # them was saved under "{base_case_id}-{domain}", which doesn't
        # match any real case, so /reports/case/{base_case_id} always
        # showed zero appeals for it.
        appeals = await _save_appeals_for_domain(user_id, base_case_id, domain.value, query, result) if save_appeals else []
        return {"domain": domain.value, "confidence": candidate["confidence"], "state": result, "appeals": appeals}

    per_domain_results = await asyncio.gather(*(run_for_candidate(c) for c in candidates))
    await _record_analysis_runs(user_id, base_case_id, per_domain_results, query)

    combined_citations: list[dict] = []
    combined_summaries: list[str] = []
    for entry in per_domain_results:
        state = entry["state"]
        for citation in state.get("structured_citations", []) or []:
            combined_citations.append({**citation, "domain": entry["domain"]})
        final = state.get("final_report") or state.get("final_answer")
        if final:
            combined_summaries.append(f"[{entry['domain']}] {final}")

    return {
        "query": query,
        "domains_analyzed": [c["domain"].value for c in candidates],
        "primary_domain": candidates[0]["domain"].value,
        "per_domain_results": {
            entry["domain"]: {
                "confidence": entry["confidence"],
                "route": entry["state"].get("route"),
                "final_report": entry["state"].get("final_report") or entry["state"].get("final_answer"),
                "agent_trace": entry["state"].get("agent_trace"),
                "appeals": entry["appeals"],
                # Each of the 6 agents' real structured output -- computed on
                # every run already (case_workflow's graph runs all of them
                # unconditionally) but previously discarded here, so the
                # frontend only ever saw the single compiled final_report
                # text blob instead of what each agent individually found.
                "agent_breakdown": _build_agent_breakdown(entry["state"]),
            }
            for entry in per_domain_results
        },
        "combined_citations": combined_citations,
        "combined_summary": "\n\n".join(combined_summaries),
    }


def _build_agent_breakdown(state: dict) -> dict:
    return {
        "research": state.get("research_output") or {},
        "evidence": state.get("evidence_output") or {},
        "knowledge_graph": {"patterns": state.get("graph_patterns") or []},
        "strategy": state.get("strategy_output") or {},
        "negotiation": state.get("negotiation_output") or {},
        "review": state.get("review_output") or {},
        # Every review pass, not just the final one -- powers the
        # self-correction timeline (what was flagged on the first pass,
        # proof the retry actually fixed it), which the single final
        # review_output above can't show since it's already the clean result.
        "review_history": state.get("review_history") or [],
        "review_retry_count": state.get("review_retry_count", 0),
    }
