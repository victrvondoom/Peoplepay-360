"""
Government domain administrative API routes.
Endpoints: /government/stats, /government/ingest, /government/ingest/status,
/government/corpus/stats, /government/corpus/search
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.knowledge_graph.factory import get_graph_store
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
GOVERNMENT_ROOT = PROJECT_ROOT / "knowledge" / "government"
GOVERNMENT_MANIFEST = GOVERNMENT_ROOT / "government_corpus_manifest.json"
GOVERNMENT_CHUNKS = GOVERNMENT_ROOT / "chunks" / "government_chunks.jsonl"

_status: Dict[str, Any] = {
    "status": "idle",
    "last_run": None,
    "documents_processed": 0,
    "chunks_created": 0,
    "errors": [],
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _iter_local_chunks() -> list[dict[str, Any]]:
    if not GOVERNMENT_CHUNKS.exists():
        return []
    records: list[dict[str, Any]] = []
    with GOVERNMENT_CHUNKS.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


async def _run_ingestion():
    global _status
    _status["status"] = "running"
    _status["errors"] = []
    try:
        import sys

        scripts = str(Path(__file__).resolve().parents[4] / "backend" / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import ingest_government

        await ingest_government.run_pipeline()
        _status["status"] = "completed"
    except Exception as exc:
        _status["status"] = "failed"
        _status["errors"].append(str(exc))


@router.post("/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks) -> Dict[str, str]:
    """Start full vector/graph ingestion. This is separate from local corpus collection."""
    if _status["status"] == "running":
        raise HTTPException(status_code=400, detail="Ingestion already running")
    background_tasks.add_task(_run_ingestion)
    return {"message": "Government vector ingestion started in background"}


@router.get("/ingest/status")
async def ingestion_status() -> Dict[str, Any]:
    """Return current vector/graph ingestion pipeline status."""
    return _status


@router.get("/corpus/stats")
async def corpus_stats() -> Dict[str, Any]:
    """Return local downloaded/chunked government corpus stats without Gemini/Qdrant."""
    manifest = _read_json(GOVERNMENT_MANIFEST, {})
    return {
        "domain": Domain.GOVERNMENT.value,
        "corpus_ready": GOVERNMENT_CHUNKS.exists(),
        "manifest_path": str(GOVERNMENT_MANIFEST.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "chunk_path": str(GOVERNMENT_CHUNKS.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "files_total": manifest.get("files_total", 0),
        "chunks_total": manifest.get("chunks_total", 0),
        "bytes_total": manifest.get("bytes_total", 0),
        "extension_counts": manifest.get("extension_counts", {}),
        "authority_counts": manifest.get("authority_counts", {}),
        "folder_counts": manifest.get("folder_counts", {}),
    }


@router.get("/corpus/search")
async def search_local_corpus(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    """Keyword search over local government chunks; no Gemini or vector DB required."""
    terms = [term.lower() for term in q.split() if term.strip()]
    scored: list[tuple[int, dict[str, Any]]] = []
    for chunk in _iter_local_chunks():
        text = chunk.get("text", "")
        lower = text.lower()
        score = sum(lower.count(term) for term in terms)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, chunk in scored[:limit]:
        text = chunk.get("text", "")
        results.append({
            "score": score,
            "source_path": chunk.get("source_path"),
            "chunk_index": chunk.get("chunk_index"),
            "metadata": chunk.get("metadata", {}),
            "snippet": text[:700],
        })
    return {"query": q, "count": len(results), "results": results}


@router.get("/stats")
async def domain_stats() -> Dict[str, Any]:
    """Return government vector/graph stats plus local corpus status."""
    try:
        vector_count = qdrant_service.count(Domain.GOVERNMENT)
    except Exception:
        vector_count = 0

    try:
        store = get_graph_store()
        driver = store._get_driver()
        with driver.session() as s:
            r = s.run(
                "MATCH (n) WHERE n.domain = $d RETURN count(n) AS cnt",
                d=Domain.GOVERNMENT.value,
            )
            entity_count = r.single()["cnt"]
    except Exception:
        entity_count = 0

    corpus = await corpus_stats()
    return {
        "domain": Domain.GOVERNMENT.value,
        "vector_chunks": vector_count,
        "graph_entities": entity_count,
        "local_corpus": corpus,
        "active_specialists": 8,
        "specialists": [
            "identity_documents",
            "travel_documents",
            "civil_certificates",
            "transport_licensing",
            "property_land_records",
            "pensions_welfare",
            "grievance_rti",
            "general_government",
        ],
    }
