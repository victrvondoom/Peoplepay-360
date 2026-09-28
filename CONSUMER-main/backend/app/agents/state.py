from __future__ import annotations

from typing import Any, TypedDict

from app.models.domain import Domain


class ResearchOutput(TypedDict, total=False):
    applicable_clauses: list[str]
    possible_exclusions: list[str]
    waiting_periods: list[str]
    regulations: list[str]
    # Subset of `regulations` that couldn't be confirmed against the actual
    # retrieved source text -- see app/services/citation_verification.py.
    # Still shown to the reader (a real regulation just phrased differently
    # than the source, or genuine model knowledge, isn't necessarily wrong),
    # but flagged rather than presented with the same unearned confidence as
    # a citation that's directly grounded in what was retrieved.
    unverified_regulations: list[str]
    summary: str
    confidence: float


class EvidenceOutput(TypedDict, total=False):
    diagnosis: str
    treatment: str
    hospital: str
    coverage_requested: str
    admission_date: str
    discharge_date: str
    bill_amount: str
    reason_for_rejection: str
    documents_missing: list[str]
    key_dates: list[str]
    summary: str


class StrategyOutput(TypedDict, total=False):
    can_appeal: str
    success_probability: float
    recommended_strategy: str
    evidence_required: list[str]
    escalation_path: list[str]
    summary: str


class NegotiationOutput(TypedDict, total=False):
    appeal_letter: str
    complaint_email: str
    escalation_note: str
    consumer_complaint: str
    summary: str


class ReviewOutput(TypedDict, total=False):
    missing_evidence: list[str]
    hallucination_risks: list[str]
    wrong_clause_risks: list[str]
    weak_arguments: list[str]
    approval_ready: bool
    summary: str


class AgentState(TypedDict, total=False):
    # Case identity
    case_id: str
    # The real, saved case's id -- only set (and different from case_id) in
    # multi-domain runs, where case_id is per-domain-suffixed for internal
    # state isolation but only one case record is ever actually saved.
    base_case_id: str
    user_id: str
    domain: Domain
    case_summary: str
    institution_name: str

    # Raw inputs
    evidence_bundle: str
    document_ids: list[str]
    documents: list[dict[str, Any]]

    # Research outputs
    retrieved_context: str
    graph_context: str
    web_search_results: list[dict[str, Any]]
    research_output: ResearchOutput
    research_summary: str
    citations: list[str]
    graph_patterns: list[dict[str, Any]]

    # Evidence outputs
    evidence_output: EvidenceOutput
    evidence_summary: str

    # Strategy outputs
    strategy_output: StrategyOutput
    strategy: str

    # Negotiation outputs
    negotiation_output: NegotiationOutput
    appeal_draft: str

    # Review outputs
    review_output: ReviewOutput
    review_notes: list[str]
    # Every review pass in order (see review_agent.py) -- powers the
    # self-correction timeline: what was flagged on pass 1, proof it was
    # resolved by the final pass.
    review_history: list[ReviewOutput]

    # Final
    final_report: str
    final_answer: str

    # Orchestration metadata
    route: str
    plan: dict[str, Any]
    agent_trace: list[str]
    specialist_outputs: list[dict[str, Any]]
    specialist_results: list[dict[str, Any]]
    llm_call_count: int
    workflow_engine: str
    # How many times review has sent the case back to strategy for a fix --
    # caps the loop so a persistently uncorrectable case still terminates
    # instead of looping until the retry limit crashes the pipeline.
    review_retry_count: int
    # Freshly re-evaluated by review_agent on every pass (not inferred from
    # review_retry_count, which stays at its capped value on a second failed
    # pass and would otherwise be indistinguishable from "just retried once").
    review_should_retry: bool

    # Phase 2: Enterprise Intelligence Layer
    candidate_domains: list[dict[str, Any]]
    memory_context: str
    scored_evidence: list[dict[str, Any]]
    structured_citations: list[dict[str, Any]]
