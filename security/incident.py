"""Incident Management"""
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from enum import Enum

from security.errors import IncidentError


class IncidentStatus(str, Enum):
    NEW = "new"
    TRIAGE = "triage"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    FALSE_POSITIVE = "false_positive"


class IncidentType(str, Enum):
    SECURITY_BREACH = "security_breach"
    DATA_LEAK = "data_leak"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    MALWARE_INFECTION = "malware_infection"
    API_ABUSE = "api_abuse"
    MISCONFIGURATION = "misconfiguration"
    COMPLIANCE_VIOLATION = "compliance_violation"
    OTHER = "other"


class IncidentManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._incidents = []
                cls._instance._lock = threading.Lock()
                cls._instance._counter = 0
            return cls._instance
    
    def create_incident(self, incident_type: str, title: str, description: str = "",
                      priority: str = "medium", detected_by: str = "system",
                      **kwargs) -> str:
        """Create a new incident."""
        self._counter += 1
        incident_id = f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{self._counter:04d}"
        
        incident = {
            "incident_id": incident_id,
            "type": incident_type,
            "title": title,
            "description": description,
            "priority": priority,
            "status": IncidentStatus.NEW.value,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "detected_by": detected_by,
            "assigned_to": None,
            "resolved_at": None,
            "resolved_by": None,
            "metadata": kwargs,
        }
        
        with self._lock:
            self._incidents.append(incident)
        
        return incident_id
    
    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Get an incident by ID."""
        with self._lock:
            for i in self._incidents:
                if i["incident_id"] == incident_id:
                    return i
            return None
    
    def update_status(self, incident_id: str, status: str, updated_by: str = "system") -> bool:
        """Update incident status."""
        with self._lock:
            for i in self._incidents:
                if i["incident_id"] == incident_id:
                    i["status"] = status
                    i["status_changed_at"] = datetime.now(timezone.utc).isoformat()
                    i["status_changed_by"] = updated_by
                    return True
            return False
    
    def assign_incident(self, incident_id: str, assigned_to: str, assigned_by: str = "system") -> bool:
        """Assign an incident."""
        with self._lock:
            for i in self._incidents:
                if i["incident_id"] == incident_id:
                    i["assigned_to"] = assigned_to
                    i["assigned_at"] = datetime.now(timezone.utc).isoformat()
                    i["assigned_by"] = assigned_by
                    return True
            return False
    
    def resolve_incident(self, incident_id: str, resolved_by: str, resolution: str = "") -> bool:
        """Resolve an incident."""
        with self._lock:
            for i in self._incidents:
                if i["incident_id"] == incident_id:
                    i["status"] = IncidentStatus.RESOLVED.value
                    i["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    i["resolved_by"] = resolved_by
                    i["resolution"] = resolution
                    return True
            return False
    
    def query_incidents(self, status: str = None, type: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Query incidents."""
        with self._lock:
            incidents = list(self._incidents)
        
        if status:
            incidents = [i for i in incidents if i["status"] == status]
        if type:
            incidents = [i for i in incidents if i["type"] == type]
        
        return incidents[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get incident statistics."""
        with self._lock:
            incidents = list(self._incidents)
        
        by_status = {}
        by_type = {}
        by_priority = {}
        
        for i in incidents:
            by_status[i["status"]] = by_status.get(i["status"], 0) + 1
            by_type[i["type"]] = by_type.get(i["type"], 0) + 1
            by_priority[i["priority"]] = by_priority.get(i["priority"], 0) + 1
        
        return {
            "total": len(incidents),
            "by_status": by_status,
            "by_type": by_type,
            "by_priority": by_priority,
            "open": sum(1 for i in incidents if i["status"] in [
                IncidentStatus.NEW.value, IncidentStatus.TRIAGE.value,
                IncidentStatus.INVESTIGATING.value, IncidentStatus.CONTAINED.value
            ]),
        }


def get_incident_manager():
    return IncidentManager()


def reset_incident_manager():
    IncidentManager._instance = None


def create_incident(incident_type, title, description="", **kwargs):
    return get_incident_manager().create_incident(incident_type, title, description, **kwargs)


def get_incident(incident_id):
    return get_incident_manager().get_incident(incident_id)


def update_incident(incident_id, **kwargs):
    manager = get_incident_manager()
    for key, value in kwargs.items():
        if hasattr(manager, f"update_{key}"):
            return getattr(manager, f"update_{key}")(incident_id, value)
    return False


def resolve_incident(incident_id, resolved_by, resolution=""):
    return get_incident_manager().resolve_incident(incident_id, resolved_by, resolution)


def close_incident(incident_id, closed_by="system"):
    return get_incident_manager().update_status(incident_id, IncidentStatus.CLOSED.value, closed_by)
