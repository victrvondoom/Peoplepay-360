"""
E-commerce domain administrative API routes.

The production corpus flow is:
1. Download official/platform sources into knowledge/ecommerce.
2. Build vetted chunks at knowledge/ecommerce/chunks/ecommerce_chunks.jsonl.
3. Build vector snapshot + graph events from those vetted chunks only.
4. Optionally migrate vector snapshot to Qdrant and graph events to Neo4j.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.knowledge_graph.factory import get_graph_store
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ECOMMERCE_ROOT = PROJECT_ROOT / "knowledge" / "ecommerce"
ECOMMERCE_MANIFEST = ECOMMERCE_ROOT / "ecommerce_corpus_manifest.json"
ECOMMERCE_CHUNKS = ECOMMERCE_ROOT / "chunks" / "ecommerce_chunks.jsonl"
ECOMMERCE_QUALITY_REPORT = ECOMMERCE_ROOT / "ecommerce_source_quality_report.json"
ECOMMERCE_VECTOR_SNAPSHOT = PROJECT_ROOT / "backend" / "datasets" / "vector_embeddings" / "proxy_ecommerce.jsonl"
GRAPH_EVENTS = PROJECT_ROOT / "backend" / "datasets" / "knowledge_graph" / "neo4j_fallback.jsonl"

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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _iter_local_chunks() -> list[dict[str, Any]]:
    return _read_jsonl(ECOMMERCE_CHUNKS)


def _count_ecommerce_graph_events() -> int:
    return sum(1 for event in _read_jsonl(GRAPH_EVENTS) if event.get("payload", {}).get("domain") == Domain.ECOMMERCE.value)


async def _run_ingestion() -> None:
    global _status
    _status = {"status": "running", "last_run": None, "documents_processed": 0, "chunks_created": 0, "errors": []}
    try:
        scripts = str(PROJECT_ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from build_ecommerce_vector_and_graph_store import append_graph_events, build_vectors

        vector_result = build_vectors()
        graph_result = append_graph_events()
        _status.update(
            {
                "status": "completed",
                "documents_processed": vector_result.get("documents", 0),
                "chunks_created": vector_result.get("points", 0),
                "vector_snapshot": vector_result,
                "graph_events": graph_result,
            }
        )
    except Exception as exc:
        _status["status"] = "failed"
        _status["errors"].append(str(exc))


@router.post("/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks) -> Dict[str, str]:
    """Build clean local vector snapshot and Neo4j fallback events from vetted e-commerce chunks."""
    if _status["status"] == "running":
        raise HTTPException(status_code=400, detail="Ingestion already running")
    background_tasks.add_task(_run_ingestion)
    return {"message": "E-commerce clean corpus vector/graph build started"}


@router.get("/ingest/status")
async def ingestion_status() -> Dict[str, Any]:
    """Return current clean vector/graph build status."""
    return _status


@router.get("/corpus/stats")
async def corpus_stats() -> Dict[str, Any]:
    """Return local downloaded/chunked e-commerce corpus stats without Gemini/Qdrant."""
    manifest = _read_json(ECOMMERCE_MANIFEST, {})
    return {
        "domain": Domain.ECOMMERCE.value,
        "corpus_ready": ECOMMERCE_CHUNKS.exists(),
        "manifest_path": str(ECOMMERCE_MANIFEST.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "chunk_path": str(ECOMMERCE_CHUNKS.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "quality_report_path": str(ECOMMERCE_QUALITY_REPORT.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "files_total": manifest.get("files_total", 0),
        "chunks_total": manifest.get("chunks_total", 0),
        "bytes_total": manifest.get("bytes_total", 0),
        "extension_counts": manifest.get("extension_counts", {}),
        "authority_counts": manifest.get("authority_counts", {}),
        "category_counts": manifest.get("category_counts", {}),
        "folder_counts": manifest.get("folder_counts", {}),
        "wikipedia_excluded": "Wikipedia" not in manifest.get("authority_counts", {}),
    }


@router.get("/corpus/vector-status")
async def vector_status() -> Dict[str, Any]:
    """Return prepared vector snapshot and graph-event status for migration readiness."""
    vectors = _read_jsonl(ECOMMERCE_VECTOR_SNAPSHOT)
    authorities = sorted({point.get("payload", {}).get("authority") for point in vectors if point.get("payload", {}).get("authority")})
    return {
        "domain": Domain.ECOMMERCE.value,
        "vector_snapshot_ready": ECOMMERCE_VECTOR_SNAPSHOT.exists(),
        "vector_snapshot_path": str(ECOMMERCE_VECTOR_SNAPSHOT.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "vector_points": len(vectors),
        "graph_events_path": str(GRAPH_EVENTS.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "ecommerce_graph_events": _count_ecommerce_graph_events(),
        "authorities": authorities,
        "qdrant_collection": "proxy_ecommerce",
        "migration_commands": [
            "python scripts/migrate_vectors_to_qdrant.py",
            "python scripts/migrate_events_to_neo4j.py",
        ],
    }


@router.get("/corpus/search")
async def search_local_corpus(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    """Keyword search over local e-commerce chunks; no Gemini or vector DB required."""
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
        results.append(
            {
                "score": score,
                "source_path": chunk.get("source_path"),
                "chunk_index": chunk.get("chunk_index"),
                "metadata": chunk.get("metadata", {}),
                "snippet": text[:700],
            }
        )
    return {"query": q, "count": len(results), "results": results}


@router.get("/stats")
async def domain_stats() -> Dict[str, Any]:
    """Return e-commerce vector/graph stats plus local corpus status."""
    try:
        vector_count = qdrant_service.count(Domain.ECOMMERCE)
    except Exception:
        vector_count = 0

    try:
        store = get_graph_store()
        driver = store._get_driver()
        with driver.session() as s:
            r = s.run("MATCH (n) WHERE n.domain = $d RETURN count(n) AS cnt", d=Domain.ECOMMERCE.value)
            entity_count = r.single()["cnt"]
    except Exception:
        entity_count = 0

    corpus = await corpus_stats()
    prepared = await vector_status()
    return {
        "domain": Domain.ECOMMERCE.value,
        "vector_chunks": vector_count,
        "graph_entities": entity_count,
        "local_corpus": corpus,
        "prepared_store": prepared,
        "active_specialists": 5,
        "specialists": [
            "consumer_protection",
            "returns_refunds",
            "marketplace_policy",
            "delivery_logistics",
            "warranty_seller",
        ],
    }
