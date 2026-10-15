"""Policy Enforcement"""
import threading
from typing import Dict, List, Any

from security.errors import PolicyError


class PolicyEnforcer:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._policies = {}
                cls._instance._lock = threading.Lock()
            return cls._instance
    
    def check_permission(self, actor_id: str, resource_type: str, action: str, 
                       context: Dict[str, Any] = None) -> bool:
        """Check if an action is allowed."""
        # Default policy: allow all for system, require auth for others
        if actor_id == "system":
            return True
        
        # Simple implementation: allow all for now
        # In production, this would check actual policies
        return True
    
    def enforce(self, actor_id: str, resource_type: str, action: str,
               context: Dict[str, Any] = None):
        """Enforce permission check, raise exception if denied."""
        if not self.check_permission(actor_id, resource_type, action, context):
            raise PolicyError(f"Access denied for {actor_id}: {action} on {resource_type}")
    
    def add_policy(self, policy_id: str, policy: Dict[str, Any]):
        """Add a policy."""
        with self._lock:
            self._policies[policy_id] = policy


def get_policy_enforcer():
    return PolicyEnforcer()


def reset_policy_enforcer():
    PolicyEnforcer._instance = None


def check_permission(actor_id, resource_type, action, context=None):
    return get_policy_enforcer().check_permission(actor_id, resource_type, action, context)


def enforce_permission(actor_id, resource_type, action, context=None):
    get_policy_enforcer().enforce(actor_id, resource_type, action, context)
