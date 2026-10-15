"""
Graph Intelligence Error Definitions
"""

from typing import Any, Dict, List, Optional


class GraphError(Exception):
    """Base exception for graph-related errors."""
    
    def __init__(self, message: str, error_type: str = "graph_error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error_type,
            "message": self.message,
            "details": self.details,
        }


class EntityNotFoundError(GraphError):
    """Raised when an entity cannot be found."""
    
    def __init__(self, entity_id: str, message: Optional[str] = None):
        self.entity_id = entity_id
        msg = message or f"Entity with ID '{entity_id}' not found"
        super().__init__(msg, error_type="entity_not_found", details={"entity_id": entity_id})


class RelationshipNotFoundError(GraphError):
    """Raised when a relationship cannot be found."""
    
    def __init__(self, relationship_id: str, message: Optional[str] = None):
        self.relationship_id = relationship_id
        msg = message or f"Relationship with ID '{relationship_id}' not found"
        super().__init__(msg, error_type="relationship_not_found", details={"relationship_id": relationship_id})


class CycleDetectedError(GraphError):
    """Raised when a cycle is detected in the graph."""
    
    def __init__(self, path: List[str], message: Optional[str] = None):
        self.path = path
        path_str = " -> ".join(path)
        msg = message or f"Cycle detected: {path_str}"
        super().__init__(msg, error_type="cycle_detected", details={"path": path})


class QueryError(GraphError):
    """Raised when a graph query fails."""
    
    def __init__(self, query: str, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.query = query
        msg = message or f"Query failed: {query[:100]}..."
        super().__init__(msg, error_type="query_error", 
                        details={"query": query[:500], **(details or {})})


class DuplicateEntityError(GraphError):
    """Raised when attempting to create a duplicate entity."""
    
    def __init__(self, entity_id: str, message: Optional[str] = None):
        self.entity_id = entity_id
        msg = message or f"Entity with ID '{entity_id}' already exists"
        super().__init__(msg, error_type="duplicate_entity", details={"entity_id": entity_id})


class InvalidRelationshipError(GraphError):
    """Raised when a relationship is invalid."""
    
    def __init__(self, source_id: str, target_id: str, message: Optional[str] = None):
        self.source_id = source_id
        self.target_id = target_id
        msg = message or f"Invalid relationship between '{source_id}' and '{target_id}'"
        super().__init__(msg, error_type="invalid_relationship", 
                        details={"source_id": source_id, "target_id": target_id})


class GraphSerializationError(GraphError):
    """Raised when graph serialization/deserialization fails."""
    
    def __init__(self, message: str = "Failed to serialize/deserialize graph", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_type="serialization_error", details=details or {})


class DisconnectedGraphError(GraphError):
    """Raised when the graph is disconnected and connectivity is required."""
    
    def __init__(self, entity_id: str, message: Optional[str] = None):
        self.entity_id = entity_id
        msg = message or f"Entity '{entity_id}' is in a disconnected component"
        super().__init__(msg, error_type="disconnected_graph", details={"entity_id": entity_id})


# Ensure all error types are available
GraphException = GraphError
