from fastapi import APIRouter, Depends
from app.agents.orchestrator.case_analysis_workflow import case_analysis_workflow
from app.agents.orchestrator.case_workflow import case_workflow
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.errors import ProxyError
from app.database.postgres.repositories import case_repository
from app.knowledge_graph.neo4j.service import knowledge_graph
from app.models.domain import ACTIVE_DOMAINS
from app.schemas.cases import AgentQuestionRequest, AgentRunRequest, AgentRunResponse, CaseStatus
from app.services.case_context import build_case_summary, build_evidence_bundle

router = APIRouter()


def agent_output(case_id: str, state: dict) -> dict:
    return {
        "case_id": case_id,
        "status": "ready_for_human_review",
        "evidence_summary": state.get("evidence_summary", ""),
        "research_summary": state.get("research_summary", ""),
        "strategy": state.get("strategy", ""),
        "appeal_draft": state.get("appeal_draft", ""),
        "review_notes": state.get("review_notes", []),
        "citations": state.get("citations", []),
        "route": state.get("route", ""),
        "agent_trace": state.get("agent_trace", []),
        "specialist_outputs": state.get("specialist_outputs", []),
        "llm_call_count": state.get("llm_call_count", 0),
        "workflow_engine": state.get("workflow_engine", ""),
        "final_report": state.get("final_report", state.get("final_answer", "")),
        "final_answer": state.get("final_answer", state.get("final_report", "")),
        "research_output": state.get("research_output"),
        "evidence_output": state.get("evidence_output"),
        "strategy_output": state.get("strategy_output"),
        "negotiation_output": state.get("negotiation_output"),
        "review_output": state.get("review_output"),
    }


@router.post("/ask", response_model=AgentRunResponse)
async def ask_healthcare_agent(payload: AgentQuestionRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    if payload.domain not in ACTIVE_DOMAINS:
        raise ProxyError(f"Domain '{payload.domain.value}' is registered but not active yet", status_code=409, code="domain_not_active")
    state = await case_analysis_workflow.run_research_only(
        {
            "case_id": "ad-hoc-question",
            "user_id": user.id,
            "domain": payload.domain,
            "case_summary": payload.question,
            "institution_name": payload.institution_name,
            "evidence_bundle": payload.question,
        }
    )
    return agent_output("ad-hoc-question", state)


@router.post("/run-case", response_model=AgentRunResponse)
async def run_case_agents(payload: AgentRunRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    case = await case_repository.get_case(payload.case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")

    await case_repository.update_case_status(case["id"], CaseStatus.ANALYZING)
    documents = await case_repository.list_documents(case["id"])
    state = await case_analysis_workflow.run({
        "case_id": case["id"],
        "user_id": user.id,
        "domain": case["domain"],
        "case_summary": build_case_summary(case, documents),
        "institution_name": case["institution_name"],
        "evidence_bundle": build_evidence_bundle(documents),
        "documents": documents,
    })
    output = agent_output(case["id"], state)
    await case_repository.add_agent_run(case["id"], "case_analysis_workflow", "completed", {"documents": len(documents)}, output)
    if payload.include_negotiation_draft and output["appeal_draft"]:
        await case_repository.add_appeal(case["id"], user.id, f"Appeal draft for {case['institution_name']}", output["appeal_draft"])
    await knowledge_graph.upsert_case_graph(case, {"documents": len(documents), "agent_output": output})
    await case_repository.update_case_status(case["id"], CaseStatus.READY_FOR_APPROVAL)
    return output


@router.get("/runs/{case_id}")
async def list_agent_runs(case_id: str, user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    case = await case_repository.get_case(case_id, user.id)
    if not case:
        raise ProxyError("Case not found", status_code=404, code="case_not_found")
    return await case_repository.list_agent_runs(case_id)
