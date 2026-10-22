"""Audit Service"""
import threading
import uuid
from datetime import datetime, timezone

from security.errors import AuditError


class AuditService:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._events = []
                cls._instance._lock = threading.Lock()
            return cls._instance
    
    def log(self, event_type, action, actor_id, resource_type, resource_id=None, 
            success=True, details=None, sensitive=False):
        """Log an audit event."""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "action": action,
            "actor_id": actor_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "details": details or {},
            "sensitive": sensitive,
        }
        with self._lock:
            self._events.append(event)
        return event["event_id"]
    
    def query(self, event_type=None, actor_id=None, resource_type=None, limit=100):
        """Query audit events."""
        with self._lock:
            events = list(self._events)
        
        if event_type:
            events = [e for e in events if e["event_type"] == event_type]
        if actor_id:
            events = [e for e in events if e["actor_id"] == actor_id]
        if resource_type:
            events = [e for e in events if e["resource_type"] == resource_type]
        
        return events[:limit]
    
    def get_summary(self):
        """Get audit summary."""
        with self._lock:
            events = list(self._events)
        
        by_type = {}
        for e in events:
            by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
        
        return {
            "total": len(events),
            "by_type": by_type,
            "success_count": sum(1 for e in events if e["success"]),
            "failure_count": sum(1 for e in events if not e["success"]),
        }


def get_audit_service():
    return AuditService()


def reset_audit_service():
    AuditService._instance = None
