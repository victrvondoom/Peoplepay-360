"""
Healthcare domain administrative API routes.
Endpoints: /healthcare/stats, /healthcare/corpus/stats, /healthcare/corpus/search

For triggering/monitoring the real NVIDIA-embedded reindex, use the generic
admin endpoints: POST /admin/reindex/healthcare, GET /admin/reindex-status.

Note: healthcare is a PUBLIC HEALTH EDUCATION domain (disease/symptom info,
preventive care, vaccination, clinical guidelines, lab reference info, drug
safety, patient rights) — not a dispute-resolution domain like the
platform's other domains. Responses are educational and evidence-based
only; they are not a diagnosis and not a substitute for professional
medical advice.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Query

from app.knowledge_graph.factory import get_graph_store
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
HEALTHCARE_ROOT = PROJECT_ROOT / "knowledge" / "healthcare"
HEALTHCARE_MANIFEST = HEALTHCARE_ROOT / "healthcare_corpus_manifest.json"
HEALTHCARE_CHUNKS = HEALTHCARE_ROOT / "chunks" / "healthcare_chunks.jsonl"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _iter_local_chunks() -> list[dict[str, Any]]:
    if not HEALTHCARE_CHUNKS.exists():
        return []
    records: list[dict[str, Any]] = []
    with HEALTHCARE_CHUNKS.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


@router.get("/corpus/stats")
async def corpus_stats() -> Dict[str, Any]:
    """Local downloaded/chunked healthcare corpus stats — no NVIDIA/Qdrant needed."""
    manifest = _read_json(HEALTHCARE_MANIFEST, {})
    return {
        "domain": Domain.HEALTHCARE.value,
        "corpus_ready": HEALTHCARE_CHUNKS.exists(),
        "manifest_path": str(HEALTHCARE_MANIFEST.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "chunk_path": str(HEALTHCARE_CHUNKS.relative_to(PROJECT_ROOT)).replace("\\", "/"),
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
    """Keyword search over local healthcare chunks; no NVIDIA or vector DB required."""
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
    """Healthcare vector/graph stats plus local corpus status."""
    try:
        vector_count = qdrant_service.count(Domain.HEALTHCARE)
    except Exception:
        vector_count = 0

    try:
        store = get_graph_store()
        driver = store._get_driver()
        with driver.session() as s:
            r = s.run(
                "MATCH (n) WHERE n.domain = $d RETURN count(n) AS cnt",
                d=Domain.HEALTHCARE.value,
            )
            entity_count = r.single()["cnt"]
    except Exception:
        entity_count = 0

    corpus = await corpus_stats()
    return {
        "domain": Domain.HEALTHCARE.value,
        "vector_chunks": vector_count,
        "graph_entities": entity_count,
        "local_corpus": corpus,
        "active_specialists": 9,
        "specialists": [
            "disease_symptom_info",
            "preventive_care_vaccination",
            "clinical_guidelines",
            "drug_safety",
            "lab_diagnostics",
            "patient_rights",
            "public_health_advisory",
            "hospital_quality",
            "general_healthcare",
        ],
    }
