import asyncio

from app.agents.orchestrator.case_analysis_workflow import case_analysis_workflow
from app.models.domain import Domain
from app.services.case_context import DocumentType, build_case_summary, build_evidence_bundle, classify_document


def test_classify_policy_document() -> None:
    assert classify_document("star_health_policy_wording.pdf") == DocumentType.POLICY


def test_classify_rejection_letter() -> None:
    assert classify_document("claim_rejection_letter.pdf") == DocumentType.REJECTION_LETTER


def test_classify_medical_report() -> None:
    assert classify_document("hospital_discharge_summary.pdf") == DocumentType.MEDICAL_REPORT


def test_case_analysis_workflow_runs_linear_pipeline() -> None:
    state = asyncio.run(
        case_analysis_workflow.run(
            {
                "case_id": "case-linear-1",
                "user_id": "user-1",
                "domain": Domain.HEALTH_INSURANCE,
                "case_summary": "Star Health denied MRI claim citing waiting period.",
                "institution_name": "Star Health and Allied Insurance",
                "evidence_bundle": "Rejection letter: MRI denied due to waiting period.",
            }
        )
    )
    trace = state.get("agent_trace", [])
    assert "case_analysis:start" in trace
    assert "research:qdrant+graph+web+gemini" in trace
    assert "evidence:gemini" in trace
    assert "graph:neo4j" in trace
    assert "strategy:gemini" in trace
    assert "negotiation:all_documents" in trace
    assert "review:gemini" in trace
    assert "final_report:gemini" in trace
    assert state.get("research_summary")
    assert state.get("evidence_summary")
    assert state.get("strategy")
    assert state.get("appeal_draft")
    assert state.get("final_report")


def test_build_case_summary_groups_documents() -> None:
    case = {"title": "MRI Denial", "institution_name": "Star Health", "summary": "Denied MRI", "jurisdiction": "IN"}
    documents = [
        {"filename": "policy.pdf", "document_type": "policy"},
        {"filename": "rejection.pdf", "document_type": "rejection_letter"},
    ]
    summary = build_case_summary(case, documents)
    assert "MRI Denial" in summary
    assert "policy" in summary
    assert "rejection_letter" in summary
