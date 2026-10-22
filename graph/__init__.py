"""
PeoplePay 360 - Graph Intelligence Layer

This module provides a coherent graph intelligence service supporting:
- Entity relationships
- Graph-backed evidence intelligence
- Relationship traversal
- Provenance tracking
- Supplier dependency graphs
- Trust relationships
- Risk propagation
- Connected transaction histories
- Agent memory relationships
- Evidence-linked decisions
- Explainable recommendations
- Graph query abstractions

Integrates with FalkorDB (existing) and provides in-memory fallback.
"""

from graph.models import (
    Entity,
    Relationship,
    EntityType,
    RelationshipType,
    Graph,
    GraphQuery,
    GraphQueryResult,
    TraversalResult,
    TrustScore,
    RiskScore,
)
from graph.service import GraphService, get_graph_service
from graph.engine import GraphEngine, get_graph_engine
from graph.analyzer import GraphAnalyzer, get_graph_analyzer
from graph.errors import (
    GraphError,
    EntityNotFoundError,
    RelationshipNotFoundError,
    CycleDetectedError,
    QueryError,
)

__all__ = [
    # Models
    "Entity",
    "Relationship",
    "EntityType",
    "RelationshipType",
    "Graph",
    "GraphQuery",
    "GraphQueryResult",
    "TraversalResult",
    "TrustScore",
    "RiskScore",
    # Services
    "GraphService",
    "get_graph_service",
    "GraphEngine",
    "get_graph_engine",
    "GraphAnalyzer",
    "get_graph_analyzer",
    # Errors
    "GraphError",
    "EntityNotFoundError",
    "RelationshipNotFoundError",
    "CycleDetectedError",
    "QueryError",
]
