from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser, get_current_user, require_admin
from app.models.domain import Domain
from app.rag.retrieval.factory import get_vector_store
from app.rag.retrieval.qdrant_service import qdrant_service
from app.knowledge_graph.factory import get_graph_store

router = APIRouter()

# Global state for simple stats tracking (in production, use DB)
admin_stats: dict[str, Any] = {
    "failed_downloads": 0,
    "duplicates_detected": 0,
    "documents": 0,
    "chunks": 0,
    "embeddings": 0,
    "banks": set(),
    "graph_nodes": 0,
    "relationships": 0,
}

@router.post("/ingest")
async def ingest(user: CurrentUser = Depends(require_admin)) -> dict:
    import subprocess
    import sys
    from pathlib import Path
    
    script_path = Path(__file__).resolve().parents[4] / "scripts" / "ingest_banking.py"
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="Ingestion script not found")
        
    # Kick off the ingestion process in the background
    subprocess.Popen([sys.executable, str(script_path)])
    
    return {"status": "Ingestion pipeline started in the background"}

@router.post("/update")
async def update(user: CurrentUser = Depends(require_admin)) -> dict:
    return {"status": "Incremental update started"}

@router.post("/reindex")
async def reindex(user: CurrentUser = Depends(require_admin)) -> dict:
    return {"status": "Reindexing started"}

@router.get("/stats")
async def get_stats(user: CurrentUser = Depends(require_admin)) -> dict:
    vector_count = get_vector_store().count(qdrant_service.collection_name(Domain.BANKING))
    graph_health = get_graph_store().health_check()
    
    return {
        "status": "active",
        "documents": admin_stats["documents"],
        "chunks": admin_stats["chunks"],
        "embeddings": vector_count,
        "banks": len(admin_stats["banks"]),
        "graph_nodes": admin_stats["graph_nodes"],
        "relationships": admin_stats["relationships"],
        "failed_downloads": admin_stats["failed_downloads"],
        "duplicates": admin_stats["duplicates_detected"],
        "graph_backend": graph_health.get("backend"),
    }

@router.get("/documents")
async def get_documents(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    # Placeholder for fetching document list from Supabase
    from app.database.postgres.repositories import case_repository
    sources = await case_repository.list_knowledge_sources(Domain.BANKING)
    return sources

@router.get("/graph")
async def get_graph(user: CurrentUser = Depends(get_current_user)) -> dict:
    # Basic graph dump or summary
    health = get_graph_store().health_check()
    return {"graph_status": health, "nodes_summary": admin_stats["graph_nodes"]}
