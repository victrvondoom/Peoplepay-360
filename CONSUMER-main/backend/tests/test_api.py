import asyncio
import tempfile
from pathlib import Path

from starlette.datastructures import UploadFile

from app.agents.orchestrator.case_workflow import case_workflow
from app.agents.research_agent.agent import rank_hits
from app.database.postgres.repositories import CaseRepository
from app.llm.gemini.service import gemini_service
from app.models.domain import ACTIVE_DOMAINS, Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.schemas.cases import CaseCreate
from app.services.insurer_document_collector import Insurer, InsurerDocumentCollector
from app.services.knowledge_ingestion import knowledge_ingestion_service
from app.services.official_health_sources import OfficialHealthSourceCollector
from app.storage.service import storage_service


def test_health_insurance_and_airlines_are_active_domains() -> None:
    assert Domain.HEALTH_INSURANCE in ACTIVE_DOMAINS
    assert Domain.AIRLINES in ACTIVE_DOMAINS


def test_case_repository_creates_healthcare_case() -> None:
    repo = CaseRepository()
    payload = CaseCreate(
        domain=Domain.HEALTH_INSURANCE,
        title="Denied MRI claim",
        institution_name="Blue Shield",
        summary="My MRI was denied as not medically necessary even though my doctor ordered it.",
        jurisdiction="US-CA",
    )
    case = asyncio.run(repo.create_case("test-user-1", payload))
    assert case["domain"] == Domain.HEALTH_INSURANCE
    assert case["status"].value == "intake"


def test_qdrant_fallback_returns_healthcare_hit() -> None:
    hits = asyncio.run(qdrant_service.search(Domain.HEALTH_INSURANCE, "MRI medical necessity", 3))
    assert hits
    assert hits[0]["metadata"]["domain"] == "health_insurance"


def test_knowledge_ingestion_reads_healthcare_seed() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        seed = root / "policy_wording" / "sample_policy.md"
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_text(
            "Health insurance policy wording. Cashless hospitalization is covered when medically necessary.",
            encoding="utf-8",
        )
        result = asyncio.run(knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, root))
    assert result["documents_found"] == 1
    assert result["documents_ingested"] == 1
    assert result["chunks_indexed"] >= 1


def test_uploaded_case_document_is_indexed() -> None:
    async def scenario() -> dict:
        case = {
            "id": "case-upload-1",
            "domain": Domain.HEALTH_INSURANCE,
            "institution_name": "Blue Shield",
            "title": "Denied MRI claim",
            "summary": "MRI denied as not medically necessary.",
        }
        content = b"Denial reason: not medically necessary. Doctor ordered MRI after conservative therapy failed."
        upload = UploadFile(filename="denial.md", file=__import__("io").BytesIO(content))
        upload.headers = {"content-type": "text/markdown"}
        return await storage_service.save_case_document("test-user-1", case, upload)

    document = asyncio.run(scenario())
    assert document["indexed"] is True
    assert document["chunks_indexed"] >= 1
    assert "Doctor ordered MRI" in document["text_extract"]


def test_case_workflow_runs_healthcare_agents() -> None:
    state = asyncio.run(
        case_workflow.run(
            {
                "case_id": "case-1",
                "user_id": "test-user-1",
                "domain": Domain.HEALTH_INSURANCE,
                "case_summary": "My MRI was denied as not medically necessary even though my doctor ordered it.",
                "institution_name": "Blue Shield",
            }
        )
    )
    assert state["evidence_summary"]
    assert state["research_summary"]
    assert state["strategy"]
    assert state["appeal_draft"]
    assert state["review_notes"]
    assert state["citations"]


def test_repository_persists_agent_run_and_appeal() -> None:
    async def scenario() -> tuple[list[dict], list[dict]]:
        repo = CaseRepository()
        payload = CaseCreate(
            domain=Domain.HEALTH_INSURANCE,
            title="Denied MRI claim",
            institution_name="Blue Shield",
            summary="MRI denied as not medically necessary.",
        )
        case = await repo.create_case("user-1", payload)
        await repo.add_agent_run(case["id"], "healthcare_case_workflow", "completed", {}, {"appeal_draft": "Draft"})
        await repo.add_appeal(case["id"], "user-1", "Appeal draft", "Draft")
        return await repo.list_agent_runs(case["id"]), await repo.list_appeals(case["id"])

    runs, appeals = asyncio.run(scenario())
    assert len(runs) == 1
    assert len(appeals) == 1


def test_official_source_collector_rejects_untrusted_domain() -> None:
    root = Path(__file__).resolve().parents[2]
    collector = OfficialHealthSourceCollector(
        root / "knowledge" / "health_insurance" / "official_sources" / "source_registry.json",
        root / "knowledge" / "health_insurance" / "official_sources",
    )
    try:
        collector.validate_url("https://example.com/random-health-blog")
    except ValueError as exc:
        assert "non-allowlisted" in str(exc)
    else:
        raise AssertionError("collector accepted a non-official source")


def test_research_ranking_prefers_irdai_over_medical_context() -> None:
    hits = rank_hits([
        {"id": "med", "score": 0.9, "text": "medical", "metadata": {"authority": "World Health Organization", "category": "medical_knowledge"}},
        {"id": "reg", "score": 0.5, "text": "reg", "metadata": {"authority": "IRDAI", "category": "health_regulation"}},
    ])
    assert hits[0]["id"] == "reg"


def test_insurer_collector_allows_only_official_domains() -> None:
    root = Path(__file__).resolve().parents[2]
    collector = InsurerDocumentCollector(
        root / "knowledge" / "health_insurance" / "insurers" / "insurer_registry.json",
        root / "knowledge" / "health_insurance" / "insurers",
    )
    insurer = Insurer("star_health", "Star", ["starhealth.in", "www.starhealth.in"], ["https://www.starhealth.in/"])
    assert collector.host_allowed(insurer, "https://www.starhealth.in/downloads/policy.pdf") is True
    assert collector.host_allowed(insurer, "https://randombroker.example/star-health-policy.pdf") is False


def test_insurer_document_classification() -> None:
    root = Path(__file__).resolve().parents[2]
    collector = InsurerDocumentCollector(
        root / "knowledge" / "health_insurance" / "insurers" / "insurer_registry.json",
        root / "knowledge" / "health_insurance" / "insurers",
    )
    assert collector.classify("https://x/policy-wording.pdf") == "policy_wording"
    assert collector.classify("https://x/claim-form.pdf") == "claim_procedure"
    assert collector.classify("https://x/waiting-period.pdf") == "waiting_period"


def test_curation_does_not_exclude_care_health_by_car_substring() -> None:
    from app.services.insurer_document_curation import is_health_relevant

    metadata = {
        "label": "Care Health Insurance",
        "url": "https://irdai.gov.in/guidelines-on-standard-individual-health-insurance-product.pdf",
        "final_url": "https://irdai.gov.in/guidelines-on-standard-individual-health-insurance-product.pdf",
        "file_path": "care_health/other_health_document/sample.pdf",
        "category": "other_health_document",
        "insurer_name": "Care Health Insurance",
        "official_domain": "irdai.gov.in",
    }
    assert is_health_relevant(metadata) is True


def test_supervisor_routes_cataract_coverage_to_policy_and_medical() -> None:
    state = asyncio.run(
        case_workflow.run(
            {
                "case_id": "case-cataract",
                "user_id": "test-user-1",
                "domain": Domain.HEALTH_INSURANCE,
                "case_summary": "Does Star Health cover cataract surgery?",
                "institution_name": "Star Health and Allied Insurance",
            }
        )
    )
    routes = [output["route"] for output in state["specialist_outputs"]]
    assert state["workflow_engine"] == "langgraph"
    assert state["route"] == "policy"
    assert "policy" in routes
    assert "medical" in routes
    assert "claims" not in routes
    assert any(step == "retrieval:qdrant" for step in state["agent_trace"])
    assert state["llm_call_count"] == len(state["specialist_outputs"]) + 5
    expected_model = gemini_service.model_for("reasoning")
    assert all(output["model"] == expected_model for output in state["specialist_outputs"])


def test_supervisor_routes_denial_to_claims_agent() -> None:
    state = asyncio.run(
        case_workflow.run(
            {
                "case_id": "case-denial",
                "user_id": "test-user-1",
                "domain": Domain.HEALTH_INSURANCE,
                "case_summary": "My cashless claim was denied during preauthorization even though the hospital submitted documents.",
                "institution_name": "Care Health Insurance",
            }
        )
    )
    routes = [output["route"] for output in state["specialist_outputs"]]
    assert state["workflow_engine"] == "langgraph"
    assert state["route"] == "claims"
    assert routes == ["claims"]
    assert "negotiator:merged-specialists" not in state["agent_trace"]
    assert state["llm_call_count"] == 6


def test_gemini_role_model_mapping_uses_optimized_defaults() -> None:
    # gemini_service is now the provider-agnostic alias (conftest pins the
    # suite to nvidia) — construct a GeminiProvider directly to test
    # Gemini-specific model mapping regardless of the active default provider.
    from app.core.config import get_settings
    from app.llm.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider(get_settings())
    assert provider.model_for("reasoning") == "gemini-2.5-flash"
    assert provider.model_for("router") == "gemini-2.5-flash-lite"
    assert provider.model_for("planner") == "gemini-2.5-flash-lite"
    assert provider.model_for("response") == "gemini-2.5-flash"
    assert provider.model_for("summarization") == "gemini-2.5-flash-lite"
    assert provider.model_for("ocr") == "gemini-2.5-flash"


