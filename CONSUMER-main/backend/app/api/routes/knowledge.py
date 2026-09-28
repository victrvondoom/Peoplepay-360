from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, get_current_user, require_admin
from app.database.postgres.repositories import case_repository
from app.models.domain import Domain
from app.services.knowledge_ingestion import knowledge_ingestion_service

router = APIRouter()


class ManualIngestRequest(BaseModel):
    insurer_name: str
    category: str = "policy_wording"


@router.post("/ingest/manual")
async def manual_ingest_upload(
    insurer_name: str,
    category: str = "policy_wording",
    file: UploadFile = File(...),
    _: CurrentUser = Depends(require_admin),
) -> dict:
    import shutil
    import tempfile
    from datetime import datetime, timezone
    from uuid import NAMESPACE_URL, uuid5

    from app.services.insurer_document_curation import is_health_relevant

    root = Path(__file__).resolve().parents[4] / "knowledge" / "health_insurance" / "insurers"
    insurer_id = insurer_name.lower().replace(" ", "_").replace("&", "and")
    for known in ["star_health", "hdfc_ergo", "niva_bupa", "icici_lombard", "care_health", "aditya_birla_health", "tata_aig", "bajaj_allianz", "reliance_general", "united_india"]:
        if known.replace("_", " ") in insurer_name.lower() or known in insurer_name.lower():
            insurer_id = known
            break

    target_dir = root / insurer_id / category
    metadata_dir = root / "metadata" / insurer_id
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "document.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    destination = target_dir / (file.filename or f"manual_{insurer_id}{suffix}")
    shutil.copy2(tmp_path, destination)
    tmp_path.unlink(missing_ok=True)

    metadata = {
        "insurer_id": insurer_id,
        "insurer_name": insurer_name,
        "category": category,
        "label": destination.name,
        "url": f"manual://{destination.name}",
        "final_url": f"manual://{destination.name}",
        "content_type": file.content_type or "application/pdf",
        "content_sha256": str(uuid5(NAMESPACE_URL, destination.as_posix())),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "file_path": str(destination),
        "official_domain": "manual_ingest",
        "ingestion_source": "manual_api",
        "health_insurance_relevant": True,
    }
    metadata["health_insurance_relevant"] = is_health_relevant(metadata)
    metadata_path = metadata_dir / f"{destination.stem}.json"
    metadata_path.write_text(__import__("json").dumps(metadata, indent=2), encoding="utf-8")

    backlog = root / "manual_ingest_backlog.jsonl"
    with backlog.open("a", encoding="utf-8") as handle:
        handle.write(__import__("json").dumps({
            "insurer_id": insurer_id,
            "insurer_name": insurer_name,
            "file_path": str(destination),
            "resolved_by": "manual_api",
            "logged_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")

    ingestion = await knowledge_ingestion_service.ingest_path(Domain.HEALTH_INSURANCE, root)
    return {"metadata": metadata, "ingestion": {
        "documents_ingested": ingestion["documents_ingested"],
        "chunks_indexed": ingestion["chunks_indexed"],
    }}


@router.post("/ingest")
async def ingest_domain_knowledge(
    domain: Domain = Domain.HEALTH_INSURANCE,
    path: str | None = None,
    _: CurrentUser = Depends(get_current_user),
) -> dict:
    knowledge_root = Path(path) if path else Path(__file__).resolve().parents[4] / "knowledge" / domain.value
    return await knowledge_ingestion_service.ingest_path(domain, knowledge_root)


@router.get("/sources")
async def list_knowledge_sources(domain: Domain | None = None, _: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return await case_repository.list_knowledge_sources(domain)


@router.get("/chunks")
async def list_knowledge_chunks(source_id: str | None = None, limit: int = 100, _: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return await case_repository.list_knowledge_chunks(source_id, limit)


@router.get("/stats")
async def knowledge_stats(domain: Domain | None = Domain.HEALTH_INSURANCE, _: CurrentUser = Depends(get_current_user)) -> dict:
    from app.rag.retrieval.factory import get_vector_store
    from app.rag.retrieval.qdrant_service import qdrant_service

    sources = await case_repository.list_knowledge_sources(domain)
    chunks = await case_repository.list_knowledge_chunks(limit=1_000_000)
    source_ids = {source["source_id"] for source in sources}
    chunks = [chunk for chunk in chunks if chunk.get("source_id") in source_ids]
    by_category: dict[str, int] = {}
    by_authority: dict[str, int] = {}
    for source in sources:
        by_category[source.get("category") or "unknown"] = by_category.get(source.get("category") or "unknown", 0) + 1
        by_authority[source.get("authority") or "unknown"] = by_authority.get(source.get("authority") or "unknown", 0) + 1
    vector_count = 0
    if domain:
        vector_count = get_vector_store().count(qdrant_service.collection_name(domain))
    return {
        "domain": domain.value if domain else None,
        "sources": len(sources),
        "chunks": len(chunks),
        "vector_points": vector_count,
        "by_category": by_category,
        "by_authority": by_authority,
    }
