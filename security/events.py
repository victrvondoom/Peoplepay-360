"""Security Event Monitoring"""
import threading
import uuid
from datetime import datetime, timezone


class SecurityMonitor:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._events = []
                cls._instance._lock = threading.Lock()
            return cls._instance
    
    def record_event(self, event_type, severity, description, actor_id=None, 
                     ip_address=None, details=None):
        """Record a security event."""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "severity": severity,
            "description": description,
            "actor_id": actor_id,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
            "acknowledged": False,
            "mitigated": False,
        }
        with self._lock:
            self._events.append(event)
        return event["event_id"]
    
    def get_events(self, event_type=None, severity=None, limit=100):
        """Get security events."""
        with self._lock:
            events = list(self._events)
        
        if event_type:
            events = [e for e in events if e["event_type"] == event_type]
        if severity:
            events = [e for e in events if e["severity"] == severity]
        
        return events[:limit]
    
    def acknowledge_event(self, event_id, acknowledged_by):
        """Acknowledge a security event."""
        with self._lock:
            for e in self._events:
                if e["event_id"] == event_id:
                    e["acknowledged"] = True
                    e["acknowledged_by"] = acknowledged_by
                    e["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
                    break
    
    def get_stats(self):
        """Get security event statistics."""
        with self._lock:
            events = list(self._events)
        
        by_type = {}
        by_severity = {}
        for e in events:
            by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
            by_severity[e["severity"]] = by_severity.get(e["severity"], 0) + 1
        
        return {
            "total": len(events),
            "by_type": by_type,
            "by_severity": by_severity,
            "unacknowledged": sum(1 for e in events if not e["acknowledged"]),
        }


def get_security_monitor():
    return SecurityMonitor()


def reset_security_monitor():
    SecurityMonitor._instance = None


def record_security_event(event_type, severity, description, **kwargs):
    return get_security_monitor().record_event(event_type, severity, description, **kwargs)
