"""
Graph Intelligence Data Models
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4


class EntityType(Enum):
    """Types of entities in the graph."""
    USER = "user"
    ORGANIZATION = "organization"
    SUPPLIER = "supplier"
    PRODUCT = "product"
    ORDER = "order"
    PAYMENT = "payment"
    TRANSACTION = "transaction"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    DECISION = "decision"
    WORKFLOW = "workflow"
    AGENT = "agent"
    TASK = "task"
    DOCUMENT = "document"
    SUSTAINABILITY_SCORE = "sustainability_score"
    RISK_ASSESSMENT = "risk_assessment"
    CATEGORY = "category"
    LOCATION = "location"
    EVENT = "event"


class RelationshipType(Enum):
    """Types of relationships between entities."""
    # Ownership and membership
    OWNS = "owns"
    MEMBER_OF = "member_of"
    MANAGES = "manages"
    
    # Commerce
    SUPPLIES = "supplies"
    SELLS = "sells"
    PURCHASES_FROM = "purchases_from"
    MANUFACTURES = "manufactures"
    DISTRIBUTES = "distributes"
    
    # Evidence and provenance
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    VERIFIES = "verifies"
    DERIVED_FROM = "derived_from"
    DEPENDS_ON = "depends_on"
    CITES = "cites"
    
    # Workflow
    PART_OF = "part_of"
    FOLLOWS = "follows"
    PRECEDES = "precedes"
    TRIGGERS = "triggers"
    REQUIRES = "requires"
    
    # Trust and risk
    TRUSTS = "trusts"
    DISTRUSTS = "distrusts"
    POSITIVE_RISK = "positive_risk"  # Increases risk
    NEGATIVE_RISK = "negative_risk"  # Reduces risk
    
    # Agent and task
    EXECUTES = "executes"
    ASSIGNED_TO = "assigned_to"
    USES = "uses"
    HAS_MEMORY = "has_memory"
    
    # General
    RELATED_TO = "related_to"
    SIMILAR_TO = "similar_to"
    CONTAINS = "contains"
    BELONGS_TO = "belongs_to"


@dataclass
class TrustScore:
    """Trust score between two entities."""
    source_id: str
    target_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    score: float = 0.0  # -1.0 to 1.0, where -1.0 is complete distrust
    confidence: float = 0.0  # 0.0 to 1.0
    last_updated: datetime = field(default_factory=datetime.utcnow)
    evidence_ids: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


@dataclass
class RiskScore:
    """Risk score for an entity."""
    entity_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    score: float = 0.0  # 0.0 to 1.0, where 1.0 is highest risk
    category: str = "general"  # e.g., "financial", "reputation", "compliance"
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)
    factors: Dict[str, float] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Entity:
    """A node in the knowledge graph."""
    entity_type: EntityType
    name: str
    id: str = field(default_factory=lambda: str(uuid4()))
    description: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Computed fields (not stored, calculated)
    trust_score: Optional[TrustScore] = None
    risk_score: Optional[RiskScore] = None
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other: Any):
        if not isinstance(other, Entity):
            return False
        return self.id == other.id


@dataclass
class Relationship:
    """An edge between two entities in the knowledge graph."""
    source_id: str  # Entity ID
    target_id: str  # Entity ID
    relationship_type: RelationshipType
    id: str = field(default_factory=lambda: str(uuid4()))
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0  # Importance/strength of the relationship
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other: Any):
        if not isinstance(other, Relationship):
            return False
        return self.id == other.id


@dataclass
class Graph:
    """Represents a subgraph or the entire knowledge graph."""
    name: str = "default"
    id: str = field(default_factory=lambda: str(uuid4()))
    description: Optional[str] = None
    entities: Dict[str, Entity] = field(default_factory=dict)
    relationships: Dict[str, Relationship] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_entity(self, entity: Entity):
        """Add an entity to the graph."""
        self.entities[entity.id] = entity
        self.updated_at = datetime.utcnow()
    
    def add_relationship(self, relationship: Relationship):
        """Add a relationship to the graph."""
        self.relationships[relationship.id] = relationship
        self.updated_at = datetime.utcnow()
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        return self.entities.get(entity_id)
    
    def get_relationship(self, relationship_id: str) -> Optional[Relationship]:
        """Get a relationship by ID."""
        return self.relationships.get(relationship_id)
    
    def get_relationships_by_type(
        self,
        relationship_type: RelationshipType,
    ) -> List[Relationship]:
        """Get all relationships of a specific type."""
        return [
            r for r in self.relationships.values()
            if r.relationship_type == relationship_type
        ]
    
    def get_outgoing_relationships(self, entity_id: str) -> List[Relationship]:
        """Get all outgoing relationships from an entity."""
        return [
            r for r in self.relationships.values()
            if r.source_id == entity_id
        ]
    
    def get_incoming_relationships(self, entity_id: str) -> List[Relationship]:
        """Get all incoming relationships to an entity."""
        return [
            r for r in self.relationships.values()
            if r.target_id == entity_id
        ]
    
    def get_related_entities(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType] = None,
        direction: str = "both",
    ) -> Dict[str, Entity]:
        """
        Get all entities related to a given entity.
        
        Args:
            entity_id: The source entity ID
            relationship_type: Filter by relationship type (optional)
            direction: "outgoing", "incoming", or "both"
            
        Returns:
            Dictionary of entity_id -> Entity
        """
        related: Dict[str, Entity] = {}
        
        for relationship in self.relationships.values():
            if relationship_type and relationship.relationship_type != relationship_type:
                continue
            
            if direction in ("outgoing", "both") and relationship.source_id == entity_id:
                if relationship.target_id in self.entities:
                    related[relationship.target_id] = self.entities[relationship.target_id]
            
            if direction in ("incoming", "both") and relationship.target_id == entity_id:
                if relationship.source_id in self.entities:
                    related[relationship.source_id] = self.entities[relationship.source_id]
        
        return related


@dataclass
class GraphQuery:
    """A query to execute on the graph."""
    query_type: str  # "cypher", "traversal", "shortest_path", "pattern", etc.
    query_string: str
    id: str = field(default_factory=lambda: str(uuid4()))
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    limit: Optional[int] = None


@dataclass
class GraphQueryResult:
    """Result of a graph query."""
    query: GraphQuery
    id: str = field(default_factory=lambda: str(uuid4()))
    results: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0.0
    executed_at: datetime = field(default_factory=datetime.utcnow)
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraversalResult:
    """Result of a graph traversal."""
    start_entity_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    end_entity_id: Optional[str] = None
    path: List[str] = field(default_factory=list)  # List of entity IDs in the path
    relationships: List[str] = field(default_factory=list)  # List of relationship IDs
    depth: int = 0
    found: bool = False
    visited: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PathResult:
    """Result of a path-finding query."""
    source_id: str
    target_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    paths: List[List[str]] = field(default_factory=list)  # List of paths, each path is list of entity IDs
    shortest_path: Optional[List[str]] = None
    shortest_path_length: int = 0
    all_relationships: List[List[RelationshipType]] = field(default_factory=list)


@dataclass
class ConnectedComponents:
    """Connected components in the graph."""
    id: str = field(default_factory=lambda: str(uuid4()))
    components: List[List[str]] = field(default_factory=list)  # List of component groups
    component_sizes: List[int] = field(default_factory=list)
    largest_component_size: int = 0
    total_components: int = 0
