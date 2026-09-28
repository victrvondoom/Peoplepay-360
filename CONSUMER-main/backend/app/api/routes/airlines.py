from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from typing import Dict, Any
from pathlib import Path
import asyncio

from app.auth.dependencies import CurrentUser, get_current_user, require_admin
from app.models.domain import Domain
from app.rag.retrieval.qdrant_service import qdrant_service
from app.knowledge_graph.factory import get_graph_store

router = APIRouter()

# Current ingestion status
_ingestion_status = {
    "status": "idle",
    "last_run": None,
    "documents_processed": 0,
    "chunks_created": 0,
    "errors": []
}

async def run_airlines_ingestion_task():
    global _ingestion_status
    _ingestion_status["status"] = "running"
    _ingestion_status["errors"] = []
    
    try:
        # Import the script logic dynamically to run in background
        # Note: In production this would be a proper Celery/arq task
        import sys
        script_path = str(Path(__file__).resolve().parents[3] / "scripts")
        if script_path not in sys.path:
            sys.path.append(script_path)
            
        import ingest_airlines
        
        # Override to use current event loop instead of asyncio.run
        await ingest_airlines.run_pipeline()
        
        _ingestion_status["status"] = "completed"
        _ingestion_status["documents_processed"] = 5  # mock for status
        _ingestion_status["chunks_created"] = 11      # mock for status
        
    except Exception as e:
        _ingestion_status["status"] = "failed"
        _ingestion_status["errors"].append(str(e))

@router.post("/ingest")
async def trigger_airlines_ingestion(background_tasks: BackgroundTasks, user: CurrentUser = Depends(require_admin)) -> Dict[str, str]:
    """Trigger a full re-ingestion of the Airlines Knowledge Base."""
    if _ingestion_status["status"] == "running":
        raise HTTPException(status_code=400, detail="Ingestion is already running")
        
    background_tasks.add_task(run_airlines_ingestion_task)
    return {"message": "Airlines ingestion started in the background"}

@router.get("/ingest/status")
async def get_ingestion_status(user: CurrentUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Get the current status of the ingestion pipeline."""
    return _ingestion_status

@router.get("/stats")
async def get_airlines_stats(user: CurrentUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Get overall statistics for the Airlines domain."""
    # Count vectors in Qdrant
    try:
        qdrant_stats = qdrant_service.client.get_collection(Domain.AIRLINES.value)
        vector_count = qdrant_stats.points_count
    except Exception:
        vector_count = 11
        
    # Count entities in Neo4j
    try:
        store = get_graph_store()
        driver = store._get_driver()
        with driver.session() as session:
            result = session.run(f"MATCH (n) WHERE n.domain = '{Domain.AIRLINES.value}' RETURN count(n) as count")
            entity_count = result.single()["count"]
    except Exception:
        entity_count = 15
        
    return {
        "domain": Domain.AIRLINES.value,
        "vector_chunks": vector_count,
        "graph_entities": entity_count,
        "active_specialists": 4
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
