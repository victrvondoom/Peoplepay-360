"""
Graph Engine

Core graph operations and in-memory graph management.
Provides fallback when FalkorDB is not available.
"""

import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from graph.models import (
    Entity,
    Relationship,
    EntityType,
    RelationshipType,
    Graph,
    TraversalResult,
    PathResult,
    ConnectedComponents,
)
from graph.errors import (
    GraphError,
    EntityNotFoundError,
    RelationshipNotFoundError,
    CycleDetectedError,
    DuplicateEntityError,
)


# Singleton instance
_engine_instance: Optional["GraphEngine"] = None
_engine_lock = threading.Lock()


class GraphEngine:
    """
    In-memory graph engine for entity and relationship management.
    
    Provides:
    - Entity CRUD operations
    - Relationship CRUD operations
    - Graph traversal
    - Path finding
    - Cycle detection
    - Connected components analysis
    """
    
    def __init__(self):
        """Initialize the graph engine."""
        self._entities: Dict[str, Entity] = {}
        self._relationships: Dict[str, Relationship] = {}
        self._lock = threading.Lock()
        self._index: Dict[EntityType, Set[str]] = {}  # Type -> Set of entity IDs
    
    def create_entity(
        self,
        entity_type: EntityType,
        name: str,
        description: Optional[str] = None,
        entity_id: Optional[str] = None,
        **properties: Any
    ) -> Entity:
        """
        Create a new entity.
        
        Args:
            entity_type: Type of the entity
            name: Human-readable name
            description: Optional description
            entity_id: Optional custom ID
            **properties: Additional properties
            
        Returns:
            The created Entity
        """
        with self._lock:
            entity_id = entity_id or str(self._generate_id())
            
            if entity_id in self._entities:
                raise DuplicateEntityError(entity_id)
            
            entity = Entity(
                id=entity_id,
                entity_type=entity_type,
                name=name,
                description=description,
                properties=properties,
            )
            
            self._entities[entity_id] = entity
            self._index.setdefault(entity_type, set()).add(entity_id)
            
            return entity
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        with self._lock:
            return self._entities.get(entity_id)
    
    def update_entity(
        self,
        entity_id: str,
        **updates: Any
    ) -> Entity:
        """Update an entity."""
        with self._lock:
            entity = self._entities.get(entity_id)
            if not entity:
                raise EntityNotFoundError(entity_id)
            
            for key, value in updates.items():
                if hasattr(entity, key):
                    setattr(entity, key, value)
                else:
                    entity.properties[key] = value
            
            entity.updated_at = datetime.utcnow()
            return entity
    
    def delete_entity(self, entity_id: str, cascade: bool = True) -> bool:
        """
        Delete an entity.
        
        Args:
            entity_id: ID of the entity to delete
            cascade: If True, also delete relationships involving this entity
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if entity_id not in self._entities:
                return False
            
            if cascade:
                # Delete all relationships involving this entity
                rels_to_delete = [
                    rid for rid, rel in self._relationships.items()
                    if rel.source_id == entity_id or rel.target_id == entity_id
                ]
                for rid in rels_to_delete:
                    del self._relationships[rid]
            
            entity = self._entities[entity_id]
            self._index[entity.entity_type].discard(entity_id)
            del self._entities[entity_id]
            
            return True
    
    def list_entities(
        self,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Entity]:
        """List entities with optional filtering."""
        with self._lock:
            if entity_type:
                entity_ids = list(self._index.get(entity_type, set()))
            else:
                entity_ids = list(self._entities.keys())
            
            return [
                self._entities[eid] for eid in entity_ids[offset:offset+limit]
                if eid in self._entities
            ]
    
    def _generate_id(self) -> int:
        """Generate a unique ID."""
        import random
        return random.randint(10**18, 10**19 - 1)
    
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
        """
        Create a relationship between two entities.
        
        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            relationship_type: Type of relationship
            relationship_id: Optional custom ID
            weight: Weight/strength of the relationship
            **properties: Additional properties
            
        Returns:
            The created Relationship
        """
        with self._lock:
            # Verify entities exist
            if source_id not in self._entities:
                raise EntityNotFoundError(source_id)
            if target_id not in self._entities:
                raise EntityNotFoundError(target_id)
            
            relationship_id = relationship_id or str(self._generate_id())
            
            if relationship_id in self._relationships:
                raise DuplicateEntityError(relationship_id)
            
            relationship = Relationship(
                id=relationship_id,
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                weight=weight,
                properties=properties,
            )
            
            self._relationships[relationship_id] = relationship
            return relationship
    
    def get_relationship(self, relationship_id: str) -> Optional[Relationship]:
        """Get a relationship by ID."""
        with self._lock:
            return self._relationships.get(relationship_id)
    
    def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a relationship."""
        with self._lock:
            if relationship_id not in self._relationships:
                return False
            del self._relationships[relationship_id]
            return True
    
    def get_relationships(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relationship_type: Optional[RelationshipType] = None,
    ) -> List[Relationship]:
        """Get relationships with optional filtering."""
        with self._lock:
            results = []
            for rel in self._relationships.values():
                if source_id and rel.source_id != source_id:
                    continue
                if target_id and rel.target_id != target_id:
                    continue
                if relationship_type and rel.relationship_type != relationship_type:
                    continue
                results.append(rel)
            return results
    
    # Traversal Operations
    
    def get_related_entities(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType] = None,
        direction: str = "both",
        max_depth: int = 1,
    ) -> Dict[str, Tuple[Entity, List[Relationship]]]:
        """
        Get all entities related to a given entity with relationship paths.
        
        Args:
            entity_id: The source entity ID
            relationship_type: Filter by relationship type
            direction: "outgoing", "incoming", or "both"
            max_depth: Maximum traversal depth
            
        Returns:
            Dictionary of entity_id -> (Entity, list of Relationships to it)
        """
        with self._lock:
            visited: Set[str] = {entity_id}
            result: Dict[str, Tuple[Entity, List[Relationship]]] = {}
            
            self._traverse(
                entity_id=entity_id,
                relationship_type=relationship_type,
                direction=direction,
                current_depth=0,
                max_depth=max_depth,
                visited=visited,
                result=result,
            )
            
            return result
    
    def _traverse(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType],
        direction: str,
        current_depth: int,
        max_depth: int,
        visited: Set[str],
        result: Dict[str, Tuple[Entity, List[Relationship]]],
    ):
        """Recursive traversal helper."""
        if current_depth >= max_depth:
            return
        
        # Get relationships
        relationships = self.get_relationships(
            source_id=entity_id if direction in ("outgoing", "both") else None,
            target_id=entity_id if direction in ("incoming", "both") else None,
            relationship_type=relationship_type,
        )
        
        for rel in relationships:
            # Determine the other end of the relationship
            other_id = rel.target_id if rel.source_id == entity_id else rel.source_id
            
            if other_id in visited:
                continue
            
            visited.add(other_id)
            
            # Add to result
            entity = self._entities.get(other_id)
            if entity:
                if other_id not in result:
                    result[other_id] = (entity, [])
                result[other_id][1].append(rel)
            
            # Recurse
            self._traverse(
                entity_id=other_id,
                relationship_type=relationship_type,
                direction=direction,
                current_depth=current_depth + 1,
                max_depth=max_depth,
                visited=visited,
                result=result,
            )
    
    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        relationship_type: Optional[RelationshipType] = None,
        max_depth: int = 10,
    ) -> PathResult:
        """
        Find the shortest path between two entities.
        
        Args:
            source_id: Starting entity ID
            target_id: Target entity ID
            relationship_type: Only traverse relationships of this type
            max_depth: Maximum search depth
            
        Returns:
            PathResult with all found paths
        """
        with self._lock:
            # BFS for shortest path
            from collections import deque
            
            queue = deque([(source_id, [source_id], [])])  # (current_id, path, relationship_path)
            visited = {source_id}
            all_paths: List[List[str]] = []
            all_relationships: List[List[RelationshipType]] = []
            
            while queue:
                current_id, path, rel_path = queue.popleft()
                
                if current_id == target_id:
                    all_paths.append(path)
                    all_relationships.append(rel_path)
                    continue
                
                if len(path) > max_depth + 1:
                    continue
                
                # Get outgoing relationships
                relationships = self.get_relationships(
                    source_id=current_id,
                    relationship_type=relationship_type,
                )
                
                for rel in relationships:
                    next_id = rel.target_id
                    if next_id in visited:
                        continue
                    
                    visited.add(next_id)
                    queue.append((
                        next_id,
                        path + [next_id],
                        rel_path + [rel.relationship_type],
                    ))
            
            shortest = min(all_paths, key=len) if all_paths else []
            
            return PathResult(
                source_id=source_id,
                target_id=target_id,
                paths=all_paths,
                shortest_path=shortest,
                shortest_path_length=len(shortest) - 1 if shortest else 0,
                all_relationships=all_relationships,
            )
    
    def detect_cycle(
        self,
        entity_id: Optional[str] = None,
    ) -> List[List[str]]:
        """
        Detect cycles in the graph.
        
        Args:
            entity_id: Start detection from this entity (optional, defaults to all)
            
        Returns:
            List of cycles found, each as a list of entity IDs
        """
        with self._lock:
            cycles: List[List[str]] = []
            visited_global: Set[str] = set()
            
            def dfs(
                current_id: str,
                path: List[str],
                visited: Set[str],
                on_stack: Set[str],
            ):
                if current_id in on_stack:
                    # Found a cycle
                    cycle_start = path.index(current_id)
                    cycle = path[cycle_start:]
                    if len(cycle) > 1:  # Single node is not a cycle
                        cycles.append(cycle)
                    return
                
                if current_id in visited:
                    return
                
                visited.add(current_id)
                on_stack.add(current_id)
                path.append(current_id)
                
                # Get all outgoing relationships
                relationships = self.get_relationships(source_id=current_id)
                for rel in relationships:
                    next_id = rel.target_id
                    dfs(next_id, path, visited, on_stack)
                
                path.pop()
                on_stack.discard(current_id)
            
            start_points = [entity_id] if entity_id else list(self._entities.keys())
            
            for start_id in start_points:
                if start_id not in visited_global:
                    dfs(start_id, [], visited_global, set())
            
            return cycles
    
    def get_connected_components(self) -> ConnectedComponents:
        """
        Find all connected components in the graph.
        
        Returns:
            ConnectedComponents with component information
        """
        with self._lock:
            from collections import deque
            
            visited: Set[str] = set()
            components: List[List[str]] = []
            
            for entity_id in self._entities:
                if entity_id not in visited:
                    # BFS to find component
                    queue = deque([entity_id])
                    component: List[str] = []
                    
                    while queue:
                        current = queue.popleft()
                        if current in visited:
                            continue
                        
                        visited.add(current)
                        component.append(current)
                        
                        # Find all connected entities
                        relationships = self.get_relationships(
                            source_id=current,
                        ) + self.get_relationships(
                            target_id=current,
                        )
                        
                        for rel in relationships:
                            other_id = rel.target_id if rel.source_id == current else rel.source_id
                            if other_id in self._entities and other_id not in visited:
                                queue.append(other_id)
                    
                    components.append(component)
            
            component_sizes = [len(c) for c in components]
            largest = max(component_sizes) if component_sizes else 0
            
            return ConnectedComponents(
                components=components,
                component_sizes=component_sizes,
                largest_component_size=largest,
                total_components=len(components),
            )
    
    def get_subgraph(
        self,
        entity_ids: List[str],
        include_relationships: bool = True,
    ) -> Graph:
        """
        Get a subgraph containing specific entities.
        
        Args:
            entity_ids: List of entity IDs to include
            include_relationships: Whether to include relationships between them
            
        Returns:
            Graph containing the requested entities and relationships
        """
        with self._lock:
            subgraph = Graph()
            
            # Add entities
            for eid in entity_ids:
                entity = self._entities.get(eid)
                if entity:
                    subgraph.add_entity(entity)
            
            # Add relationships
            if include_relationships:
                for rel in self._relationships.values():
                    if rel.source_id in entity_ids and rel.target_id in entity_ids:
                        subgraph.add_relationship(rel)
            
            return subgraph
    
    def statistics(self) -> Dict[str, Any]:
        """Get graph statistics."""
        with self._lock:
            return {
                "entity_count": len(self._entities),
                "relationship_count": len(self._relationships),
                "entity_types": {
                    et.value: len(self._index.get(et, set()))
                    for et in EntityType
                },
                "relationship_types": {
                    rt.value: len([
                        r for r in self._relationships.values()
                        if r.relationship_type == rt
                    ])
                    for rt in RelationshipType
                },
                "connected_components": self.get_connected_components().total_components,
            }
    
    def clear(self) -> None:
        """Clear all entities and relationships."""
        with self._lock:
            self._entities.clear()
            self._relationships.clear()
            self._index.clear()


def get_graph_engine() -> GraphEngine:
    """Get the singleton graph engine instance."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = GraphEngine()
    return _engine_instance
