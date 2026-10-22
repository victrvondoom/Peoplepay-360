"""
Graph Service

Main service interface for graph intelligence operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from graph.models import (
    Entity,
    Relationship,
    EntityType,
    RelationshipType,
    Graph,
    GraphQuery,
    GraphQueryResult,
    TraversalResult,
    PathResult,
    ConnectedComponents,
    TrustScore,
    RiskScore,
)
from graph.engine import get_graph_engine, GraphEngine
from graph.analyzer import get_graph_analyzer, GraphAnalyzer
from graph.errors import (
    GraphError,
    EntityNotFoundError,
    RelationshipNotFoundError,
    CycleDetectedError,
    QueryError,
)


# Singleton instance
_graph_service_instance: Optional["GraphService"] = None


class GraphService:
    """
    Main graph service providing a unified API for all graph operations.
    
    Integrates:
    - GraphEngine for entity and relationship management
    - GraphAnalyzer for trust, risk, and recommendation analysis
    """
    
    def __init__(
        self,
        engine: Optional[GraphEngine] = None,
        analyzer: Optional[GraphAnalyzer] = None,
    ):
        """Initialize the graph service."""
        self.engine = engine or get_graph_engine()
        self.analyzer = analyzer or get_graph_analyzer()
    
    # Entity Operations
    
    def create_entity(
        self,
        entity_type: EntityType,
        name: str,
        description: Optional[str] = None,
        entity_id: Optional[str] = None,
        **properties: Any
    ) -> Entity:
        """Create a new entity."""
        return self.engine.create_entity(
            entity_type=entity_type,
            name=name,
            description=description,
            entity_id=entity_id,
            **properties
        )
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        return self.engine.get_entity(entity_id)
    
    def update_entity(self, entity_id: str, **updates: Any) -> Entity:
        """Update an entity."""
        return self.engine.update_entity(entity_id, **updates)
    
    def delete_entity(self, entity_id: str, cascade: bool = True) -> bool:
        """Delete an entity."""
        return self.engine.delete_entity(entity_id, cascade)
    
    def list_entities(
        self,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        """List entities with optional filtering."""
        return self.engine.list_entities(entity_type, limit, offset)
    
    # Relationship Operations
    
    def create_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType,
        relationship_id: Optional[str] = None,
        weight: float = 1.0,
        **properties: Any
    ) -> Relationship:
        """Create a relationship between two entities."""
        return self.engine.create_relationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            relationship_id=relationship_id,
            weight=weight,
            **properties
        )
    
    def get_relationship(self, relationship_id: str) -> Optional[Relationship]:
        """Get a relationship by ID."""
        return self.engine.get_relationship(relationship_id)
    
    def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a relationship."""
        return self.engine.delete_relationship(relationship_id)
    
    def get_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[RelationshipType] = None,
    ) -> List[Relationship]:
        """Get relationships with optional filtering."""
        return self.engine.get_relationships(source_id, target_id, relationship_type)
    
    # Traversal Operations
    
    def get_related_entities(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType] = None,
        direction: str = "both",
        max_depth: int = 1,
    ) -> Dict[str, Tuple[Entity, List[Relationship]]]:
        """Get all entities related to a given entity."""
        return self.engine.get_related_entities(
            entity_id=entity_id,
            relationship_type=relationship_type,
            direction=direction,
            max_depth=max_depth,
        )
    
    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        relationship_type: Optional[RelationshipType] = None,
        max_depth: int = 10,
    ) -> PathResult:
        """Find the shortest path between two entities."""
        return self.engine.shortest_path(
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            max_depth=max_depth,
        )
    
    def detect_cycle(
        self,
        entity_id: Optional[str] = None,
    ) -> List[List[str]]:
        """Detect cycles in the graph."""
        return self.engine.detect_cycle(entity_id)
    
    def get_connected_components(self) -> ConnectedComponents:
        """Get all connected components in the graph."""
        return self.engine.get_connected_components()
    
    def get_subgraph(
        self,
        entity_ids: List[str],
        include_relationships: bool = True,
    ) -> Graph:
        """Get a subgraph containing specific entities."""
        return self.engine.get_subgraph(entity_ids, include_relationships)
    
    # Analysis Operations
    
    def calculate_trust_score(
        self,
        entity_id: str,
        max_depth: int = 3,
    ) -> TrustScore:
        """Calculate trust score for an entity."""
        return self.analyzer.calculate_trust_score(entity_id, max_depth)
    
    def calculate_risk_score(
        self,
        entity_id: str,
        category: str = "general",
        max_depth: int = 3,
    ) -> RiskScore:
        """Calculate risk score for an entity."""
        return self.analyzer.calculate_risk_score(entity_id, category, max_depth)
    
    def propagate_trust(
        self,
        source_id: str,
        initial_trust: float = 1.0,
        max_depth: int = 5,
    ) -> Dict[str, TrustScore]:
        """Propagate trust from a source entity."""
        return self.analyzer.propagate_trust(source_id, initial_trust, max_depth)
    
    # Supplier Analysis
    
    def get_supplier_dependencies(
        self,
        supplier_id: str,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """Analyze dependencies for a supplier."""
        return self.analyzer.get_supplier_dependencies(supplier_id, max_depth)
    
    # Transaction Analysis
    
    def get_connected_transactions(
        self,
        transaction_id: str,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """Get all transactions connected to a given transaction."""
        return self.analyzer.get_connected_transactions(transaction_id, max_depth)
    
    # Recommendation Generation
    
    def generate_supplier_recommendations(
        self,
        user_id: str,
        requirements: Dict[str, Any],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Generate supplier recommendations."""
        return self.analyzer.generate_supplier_recommendations(
            user_id, requirements, limit
        )
    
    # Evidence Intelligence
    
    def explain_decision(
        self,
        decision_id: str,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """Generate an explanation for a decision."""
        return self.analyzer.explain_decision(decision_id, max_depth)
    
    # Health Check
    
    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the graph service."""
        stats = self.engine.statistics()
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "graph_stats": stats,
            "analyzer": "OK",
        }
    
    def statistics(self) -> Dict[str, Any]:
        """Get graph statistics."""
        return self.engine.statistics()
    
    def clear(self) -> None:
        """Clear all graph data and caches."""
        self.engine.clear()
        self.analyzer.clear_cache()


def get_graph_service() -> GraphService:
    """Get the singleton graph service instance."""
    global _graph_service_instance
    if _graph_service_instance is None:
        _graph_service_instance = GraphService()
    return _graph_service_instance
