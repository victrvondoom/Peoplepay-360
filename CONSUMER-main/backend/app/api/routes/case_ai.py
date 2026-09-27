from __future__ import annotations

from app.agents.orchestrator.case_analysis_workflow import case_analysis_workflow
from app.agents.research_agent.agent import rank_hits
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.llm.service import llm_service
from app.models.domain import ACTIVE_DOMAINS, Domain
from app.prompts.consumer_advocacy import build_agent_prompt
from app.rag.retrieval.qdrant_service import qdrant_service
from app.schemas.case_ai import (
    AnalyzeCaseRequest,
    AppealCaseRequest,
    CaseAnalysisResponse,
    CaseDetailResponse,
    CaseHistoryResponse,
    ChatCaseRequest,
    ResearchCaseRequest,
)
from app.schemas.cases import CaseStatus
from app.services.case_context import build_case_summary, build_evidence_bundle
from app.services.citation_engine import build_citations
from app.storage.service import storage_service
from fastapi import APIRouter, Depends, File, Form, UploadFile

router = APIRouter()


def _analysis_response(case_id: str, state: dict) -> dict:
    return {
        "case_id": case_id,
        "status": CaseStatus.READY_FOR_APPROVAL.value,
        "research_summary": state.get("research_summary", ""),
        "evidence_summary": state.get("evidence_summary", ""),
        "strategy": state.get("strategy", ""),
        "appeal_draft": state.get("appeal_draft", ""),
        "review_notes": state.get("review_notes", []),
        "final_report": state.get("final_report", state.get("final_answer", "")),
        "citations": state.get("citations", []),
        "agent_trace": state.get("agent_trace", []),
        "llm_call_count": state.get("llm_call_count", 0),
        "workflow_engine": state.get("workflow_engine", ""),
        "embedding_mode": llm_service.embedding_mode(),
        "research_output": state.get("research_output"),
        "evidence_output": state.get("evidence_output"),
        "strategy_output": state.get("strategy_output"),
        "negotiation_output": state.get("negotiation_output"),
        "review_output": state.get("review_output"),
        # Computed by the agents already but previously dropped before it
        # ever reached the response -- structured_citations carries a real
        # confidence score + verified/unverified flag per source (the Trust
        # & Provenance layer), graph_patterns carries cross-case
        # institutional intelligence, and review_history/review_retry_count
        # expose the self-correction loop instead of only ever showing its
        # final, already-clean result.
        "structured_citations": state.get("structured_citations", []),
        "graph_patterns": state.get("graph_patterns", []),
        "review_retry_count": state.get("review_retry_count", 0),
        "review_history": state.get("review_history", []),
    }


async def _build_state(case: dict, user_id: str, documents: list[dict]) -> dict:
    return {
        "case_id": case["id"],
        "user_id": user_id,
        "domain": case["domain"],
        "case_summary": build_case_summary(case, documents),
        "institution_name": case["institution_name"],
        "evidence_bundle": build_evidence_bundle(documents, domain=case["domain"]),
        "documents": documents,
    }


async def _get_case_or_404(case_id: str, user_id: str) -> dict:
    case = await case_repository.get_case(case_id, user_id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    return case


@router.post("/upload", response_model=dict)
async def upload_case_document(
    case_id: str = Form(...),
    document_type: str | None = Form(default=None),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    case = await _get_case_or_404(case_id, user.id)
    return await storage_service.save_case_document(user.id, case, file, document_type=document_type)


@router.post("/analyze", response_model=CaseAnalysisResponse)
async def analyze_case(payload: AnalyzeCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    case = await _get_case_or_404(payload.case_id, user.id)
    if case["domain"] not in ACTIVE_DOMAINS:
        raise ProxyError("Domain not active", status_code=409, code="domain_not_active")

    documents = await case_repository.list_documents(case["id"])
    await case_repository.update_case_status(case["id"], CaseStatus.ANALYZING)
    state = await case_analysis_workflow.run(await _build_state(case, user.id, documents))
    output = _analysis_response(case["id"], state)

    await case_repository.add_agent_run(case["id"], "case_analysis_workflow", "completed", {"documents": len(documents)}, output)
    if output["appeal_draft"]:
        await case_repository.add_appeal(case["id"], user.id, f"Appeal draft for {case['institution_name']}", output["appeal_draft"])
    await knowledge_graph.upsert_case_graph(case, {"documents": len(documents), "analysis": output})
    await case_repository.update_case_status(case["id"], CaseStatus.READY_FOR_APPROVAL)
    return output


@router.post("/research", response_model=CaseAnalysisResponse)
async def research_case(payload: ResearchCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    case = await _get_case_or_404(payload.case_id, user.id)
    documents = await case_repository.list_documents(case["id"])
    state = await case_analysis_workflow.run_research_only(await _build_state(case, user.id, documents))
    output = _analysis_response(case["id"], state)
    await case_repository.add_agent_run(case["id"], "research_only", "completed", {}, output)
    return output


@router.post("/appeal", response_model=CaseAnalysisResponse)
async def generate_appeal(payload: AppealCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    case = await _get_case_or_404(payload.case_id, user.id)
    documents = await case_repository.list_documents(case["id"])
    state = await case_analysis_workflow.run_appeal_only(await _build_state(case, user.id, documents))
    output = _analysis_response(case["id"], state)
    if output["appeal_draft"]:
        await case_repository.add_appeal(case["id"], user.id, f"Appeal draft for {case['institution_name']}", output["appeal_draft"])
    await case_repository.add_agent_run(case["id"], "appeal_only", "completed", {}, output)
    return output


@router.post("/chat", response_model=dict)
async def chat_about_case(payload: ChatCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Follow-up Q&A on an existing case. This does its own fresh retrieval
    for the specific question asked -- not just a bare LLM call over the
    original analysis -- because a follow-up question ("what's the deadline
    to escalate?", "does this exclusion apply to my case?") is often about
    something the initial research pass never searched for. Reusing only
    the stale research_summary silently degraded this into a generic
    ungrounded chatbot reply for anything outside that original scope."""
    case = await _get_case_or_404(payload.case_id, user.id)
    documents = await case_repository.list_documents(case["id"])
    runs = await case_repository.list_agent_runs(case["id"])
    latest = runs[-1]["output"] if runs else {}
    domain: Domain = case["domain"]
    institution = case.get("institution_name") or ""

    # --- Fresh retrieval scoped to the actual question, same rigor as the
    # research agent: real Qdrant search + authority-boosted ranking +
    # Neo4j institution patterns, not a bare LLM call. ---
    hits = await qdrant_service.search(domain, f"{payload.message} {institution}", limit=8)
    ranked = rank_hits(hits)[:8]
    retrieved_context = "\n\n".join(
        f"Source: {hit.get('metadata', {}).get('title') or hit.get('metadata', {}).get('filename') or hit['id']}\n"
        f"Authority: {hit.get('metadata', {}).get('authority') or hit.get('metadata', {}).get('insurer_name', 'unknown')}\n"
        f"Citation: {hit.get('metadata', {}).get('final_url') or hit.get('metadata', {}).get('source_path') or hit['id']}\n"
        f"Text: {hit.get('text', '')[:1500]}"
        for hit in ranked
    )
    patterns = await knowledge_graph.find_institution_patterns(domain, institution)
    graph_context = "\n".join(p.get("pattern", "") for p in patterns if p.get("pattern"))
    if graph_context:
        retrieved_context = f"{retrieved_context}\n\nGraph memory:\n{graph_context}".strip()
    prior_research = latest.get("research_summary", "")
    if prior_research:
        retrieved_context = f"{retrieved_context}\n\nEarlier case research:\n{prior_research}".strip()

    evidence_bundle = build_evidence_bundle(documents, domain=domain)
    prompt = build_agent_prompt(
        domain,
        f"Answer the user's follow-up question about this case completely -- with the same rigor and "
        f"citation discipline as the main case analysis, not a shortened chat reply. If the retrieved "
        f"context or evidence answers it, give the specific clause/rule/deadline/contact, not a vague "
        f"pointer to \"the relevant policy\".\nQuestion: {payload.message}",
        build_case_summary(case, documents),
        retrieved_context,
        evidence_bundle,
    )
    answer = await llm_service.generate(prompt, temperature=0.2, purpose="response")

    structured_citations = build_citations(domain, ranked)
    citations = [
        hit.get("metadata", {}).get("final_url") or hit.get("metadata", {}).get("source_path") or str(hit.get("id"))
        for hit in ranked
    ]

    await case_repository.add_event(
        case["id"],
        {"actor": "user", "event_type": "chat", "title": "Case chat", "body": payload.message},
    )
    return {
        "case_id": case["id"],
        "question": payload.message,
        "answer": answer,
        "citations": citations,
        "structured_citations": structured_citations,
        "graph_patterns": patterns,
        "agent_trace": ["chat:qdrant+graph+gemini"],
    }


@router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case_detail(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    case = await _get_case_or_404(case_id, user.id)
    documents = await case_repository.list_documents(case_id)
    runs = await case_repository.list_agent_runs(case_id)
    appeals = await case_repository.list_appeals(case_id)
    return {
        "case": case,
        "documents": documents,
        "latest_analysis": runs[-1]["output"] if runs else None,
        "appeals": appeals,
    }


@router.get("/{case_id}/history", response_model=CaseHistoryResponse)
async def get_case_history(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    await _get_case_or_404(case_id, user.id)
    return {
        "case_id": case_id,
        "events": await case_repository.list_events(case_id),
        "agent_runs": await case_repository.list_agent_runs(case_id),
        "appeals": await case_repository.list_appeals(case_id),
    }
