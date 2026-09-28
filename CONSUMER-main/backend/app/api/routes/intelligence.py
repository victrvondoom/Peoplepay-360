"""Enterprise Intelligence Layer API surface: cross-domain classification,
global (multi-domain) retrieval, the multi-domain case workflow, and tool
execution -- the Phase 2 capabilities on top of the existing per-domain
/search and /cases endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.orchestrator.multi_domain_workflow import run_multi_domain_case
from app.agents.role_agents.domain_router import classify_domains_multilingual
from app.agents.tools.registry import tool_registry
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.errors import ProxyError
from app.models.domain import Domain
from app.rag.retrieval.global_retrieval import global_search

router = APIRouter()


class ClassifyRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)


@router.post("/classify")
async def classify(payload: ClassifyRequest, _: CurrentUser = Depends(get_current_user)) -> dict:
    """Which domain(s) a raw query belongs to, with confidence scores."""
    candidates = await classify_domains_multilingual(payload.query)
    return {
        "query": payload.query,
        "candidates": [{"domain": c["domain"].value, "confidence": c["confidence"], "matched_terms": c["matched_terms"]} for c in candidates],
    }


class GlobalSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    domains: list[Domain] | None = None
    top_k_per_domain: int = Field(default=5, ge=1, le=20)
    top_k_overall: int = Field(default=15, ge=1, le=50)


@router.post("/search")
async def search_all_domains(payload: GlobalSearchRequest, _: CurrentUser = Depends(get_current_user)) -> dict:
    """Search across multiple (or all active) domains at once, ranked by
    the Evidence Scoring Engine rather than raw similarity alone."""
    return await global_search(payload.query, payload.domains, payload.top_k_per_domain, payload.top_k_overall)


class MultiDomainCaseRequest(BaseModel):
    case_id: str
    case_summary: str = Field(min_length=3, max_length=5000)
    institution_name: str | None = None
    generate_appeals: bool = False
    document_ids: list[str] = Field(default_factory=list)


@router.post("/cases/multi-domain")
async def run_multi_domain(payload: MultiDomainCaseRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Classify the query into every relevant domain and run the full case
    workflow for each concurrently, merging the results -- e.g. a cancelled
    flight with a rejected travel-insurance claim runs Airlines AND Health
    Insurance and returns both, instead of forcing a single domain choice.

    generate_appeals=True additionally persists every non-empty document the
    negotiation agent produced (appeal letter, complaint email, escalation
    note, consumer complaint) as real Appeal records, visible via GET
    /appeals and per-domain in this response's per_domain_results[*].appeals.

    document_ids -- the specific documents the caller uploaded for this run
    (scoped to user.id regardless of which case/vault they're attached to) --
    get their real extracted text pulled into the Evidence Agent's input,
    instead of every domain silently ignoring uploaded evidence and just
    re-reading case_summary."""
    return await run_multi_domain_case({
        "case_id": payload.case_id,
        "user_id": user.id,
        "case_summary": payload.case_summary,
        # Normalize None to "" here, at the boundary where user input enters
        # the pipeline -- state.get("institution_name", "") downstream does
        # NOT fall back to "" when the key is present with value None (that
        # default only applies when the key is missing), so an explicit None
        # here previously reached str-only code (cache-key hashing) and crashed.
        "institution_name": payload.institution_name or "",
        "document_ids": payload.document_ids,
    }, save_appeals=payload.generate_appeals)


@router.get("/tools")
async def list_tools(_: CurrentUser = Depends(get_current_user)) -> dict:
    return {"tools": tool_registry.list_tools()}


class ToolCallRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)


@router.post("/tools/{tool_name}/call")
async def call_tool(tool_name: str, payload: ToolCallRequest, _: CurrentUser = Depends(get_current_user)) -> dict:
    result = await tool_registry.call(tool_name, **payload.arguments)
    if not result["ok"] and result.get("error", "").startswith("Unknown tool"):
        raise ProxyError(result["error"], status_code=404, code="unknown_tool")
    return result
