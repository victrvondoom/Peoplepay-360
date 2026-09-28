from pydantic import BaseModel, Field

from app.models.domain import Domain
from app.schemas.cases import CaseStatus


class AnalyzeCaseRequest(BaseModel):
    case_id: str


class ResearchCaseRequest(BaseModel):
    case_id: str


class AppealCaseRequest(BaseModel):
    case_id: str


class ChatCaseRequest(BaseModel):
    case_id: str
    message: str = Field(min_length=2, max_length=2000)


class CaseAnalysisResponse(BaseModel):
    case_id: str
    status: str
    research_summary: str = ""
    evidence_summary: str = ""
    strategy: str = ""
    appeal_draft: str = ""
    review_notes: list[str] = Field(default_factory=list)
    final_report: str = ""
    citations: list[str] = Field(default_factory=list)
    agent_trace: list[str] = Field(default_factory=list)
    llm_call_count: int = 0
    workflow_engine: str = ""
    embedding_mode: str = ""
    research_output: dict | None = None
    evidence_output: dict | None = None
    strategy_output: dict | None = None
    negotiation_output: dict | None = None
    review_output: dict | None = None


class CaseDetailResponse(BaseModel):
    case: dict
    documents: list[dict]
    latest_analysis: dict | None = None
    appeals: list[dict] = Field(default_factory=list)


class CaseHistoryResponse(BaseModel):
    case_id: str
    events: list[dict]
    agent_runs: list[dict]
    appeals: list[dict]
