from functools import lru_cache

from app.core.config import get_settings
from app.knowledge_graph.graph_store import GraphStore
from app.knowledge_graph.jsonl_graph_store import JsonlGraphStore
from app.knowledge_graph.neo4j_graph_store import Neo4jGraphStore


@lru_cache
def get_graph_store() -> GraphStore:
    settings = get_settings()
    if settings.graph_store_backend == "neo4j":
        return Neo4jGraphStore()
    return JsonlGraphStore()


def validate_graph_store_startup() -> None:
    settings = get_settings()
    if settings.environment == "production" and settings.graph_store_backend != "neo4j":
        raise RuntimeError("Production requires GRAPH_STORE_BACKEND=neo4j")
    if settings.graph_store_backend != "neo4j":
        return
    store = get_graph_store()
    health = store.health_check()
    if health.get("status") != "ready":
        raise RuntimeError(f"Neo4j health check failed at {settings.neo4j_uri}: {health.get('error', 'unknown')}")
