"""
Feature Flag Manager

Manages feature flags for enabling/disabling functionality across the platform.
"""

import threading
import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime

from plugins.models import FeatureFlag
from plugins.errors import (
    FeatureFlagNotFoundError,
    FeatureDisabledError,
)


# Singleton instance
_feature_flag_instance: Optional["FeatureFlagManager"] = None


class FeatureFlagManager:
    """
    Manages feature flags for the platform.
    
    Provides:
    - Feature flag registration and management
    - Flag evaluation with conditions
    - Percentage-based rollouts
    - User/organization-specific flag targeting
    - Audit logging for flag changes
    """
    
    def __init__(self):
        """Initialize the feature flag manager."""
        self._flags: Dict[str, FeatureFlag] = {}
        self._flag_users: Dict[str, Set[str]] = {}  # flag_name -> set of user_ids
        self._flag_orgs: Dict[str, Set[str]] = {}  # flag_name -> set of org_ids
        self._flag_groups: Dict[str, Set[str]] = {}  # group_name -> set of user_ids
        self._lock = threading.Lock()
        self._change_history: List[Tuple[str, datetime, str, Any]] = []  # flag_name, timestamp, action, old_value
    
    def register_flag(
        self,
        name: str,
        description: str = "",
        enabled: bool = False,
        rollout_percentage: float = 0.0,
        conditions: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        environment: str = "production",
        created_by: Optional[str] = None,
    ) -> FeatureFlag:
        """
        Register a new feature flag.
        
        Args:
            name: Unique flag name
            description: Description of the flag
            enabled: Whether the flag is enabled by default
            rollout_percentage: Percentage of users to enable (0-100)
            conditions: Optional conditions for enabling
            tags: Optional tags for categorization
            environment: Environment (production, staging, development)
            created_by: User who created the flag
            
        Returns:
            The registered FeatureFlag
        """
        with self._lock:
            if name in self._flags:
                raise ValueError(f"Feature flag '{name}' already exists")
            
            flag = FeatureFlag(
                name=name,
                description=description,
                enabled=enabled,
                rollout_percentage=rollout_percentage,
                conditions=conditions or {},
                tags=tags or [],
                environment=environment,
                created_by=created_by,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            
            self._flags[name] = flag
            self._flag_users[name] = set()
            self._flag_orgs[name] = set()
            
            # Log the change
            self._log_change(name, "register", None, flag.to_dict() if hasattr(flag, 'to_dict') else str(flag))
            
            return flag
    
    def get_flag(self, name: str) -> Optional[FeatureFlag]:
        """Get a feature flag by name."""
        with self._lock:
            return self._flags.get(name)
    
    def list_flags(
        self,
        environment: Optional[str] = None,
        tag: Optional[str] = None,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> List[FeatureFlag]:
        """List feature flags with optional filtering."""
        with self._lock:
            flags = list(self._flags.values())
            
            if environment:
                flags = [f for f in flags if f.environment == environment]
            
            if tag:
                flags = [f for f in flags if tag in f.tags]
            
            if enabled_only:
                flags = [f for f in flags if f.enabled]
            
            return flags[:limit]
    
    def update_flag(
        self,
        name: str,
        enabled: Optional[bool] = None,
        rollout_percentage: Optional[float] = None,
        conditions: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        updated_by: Optional[str] = None,
    ) -> FeatureFlag:
        """
        Update a feature flag.
        
        Args:
            name: Flag name
            enabled: New enabled state
            rollout_percentage: New rollout percentage
            conditions: New conditions
            description: New description
            tags: New tags
            updated_by: User who updated the flag
            
        Returns:
            The updated FeatureFlag
        """
        with self._lock:
            flag = self._flags.get(name)
            if not flag:
                raise FeatureFlagNotFoundError(name)
            
            # Track old values
            old_values = {
                "enabled": flag.enabled,
                "rollout_percentage": flag.rollout_percentage,
                "conditions": flag.conditions,
                "description": flag.description,
                "tags": flag.tags,
            }
            
            # Update
            if enabled is not None:
                flag.enabled = enabled
            if rollout_percentage is not None:
                flag.rollout_percentage = rollout_percentage
            if conditions is not None:
                flag.conditions = conditions
            if description is not None:
                flag.description = description
            if tags is not None:
                flag.tags = tags
            if updated_by:
                flag.updated_by = updated_by
            
            flag.updated_at = datetime.utcnow()
            
            # Log the change
            self._log_change(name, "update", old_values, flag.to_dict() if hasattr(flag, 'to_dict') else str(flag))
            
            return flag
    
    def delete_flag(self, name: str) -> bool:
        """
        Delete a feature flag.
        
        Args:
            name: Flag name
            
        Returns:
            True if deleted
        """
        with self._lock:
            if name not in self._flags:
                return False
            
            flag = self._flags[name]
            del self._flags[name]
            del self._flag_users[name]
            del self._flag_orgs[name]
            
            # Log the change
            self._log_change(name, "delete", flag.to_dict() if hasattr(flag, 'to_dict') else str(flag), None)
            
            return True
    
    def is_enabled(
        self,
        name: str,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        environment: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check if a feature flag is enabled for a given context.
        
        Args:
            name: Flag name
            user_id: Optional user ID for user-specific checks
            organization_id: Optional organization ID for org-specific checks
            environment: Optional environment override
            context: Optional additional context for condition evaluation
            
        Returns:
            True if the feature is enabled
        """
        with self._lock:
            flag = self._flags.get(name)
            if not flag:
                raise FeatureFlagNotFoundError(name)
            
            # Check environment
            check_env = environment or flag.environment
            if check_env != "production" and flag.environment == "production":
                # Production flags only work in production
                return False
            
            # Check user-specific enablement (works even if flag is disabled globally)
            if user_id and user_id in self._flag_users.get(name, set()):
                return True
            
            # Check organization-specific enablement (works even if flag is disabled globally)
            if organization_id and organization_id in self._flag_orgs.get(name, set()):
                return True
            
            # If flag is disabled and no specific overrides, return False
            if not flag.enabled:
                return False
            
            # Check rollout percentage
            if flag.rollout_percentage > 0:
                if user_id:
                    # Use consistent hashing for rollout
                    if self._is_in_rollout(user_id, flag.rollout_percentage):
                        return True
            
            # Check conditions
            if flag.conditions:
                if not self._evaluate_conditions(flag.conditions, context or {}):
                    return False
            
            return True
    
    def enable_for_user(self, flag_name: str, user_id: str) -> bool:
        """
        Enable a feature flag for a specific user.
        
        Args:
            flag_name: Flag name
            user_id: User ID
            
        Returns:
            True if successful
        """
        with self._lock:
            if flag_name not in self._flags:
                raise FeatureFlagNotFoundError(flag_name)
            
            self._flag_users[flag_name].add(user_id)
            self._log_change(flag_name, "enable_user", None, {"user_id": user_id})
            return True
    
    def disable_for_user(self, flag_name: str, user_id: str) -> bool:
        """
        Disable a feature flag for a specific user.
        
        Args:
            flag_name: Flag name
            user_id: User ID
            
        Returns:
            True if successful
        """
        with self._lock:
            if flag_name not in self._flags:
                raise FeatureFlagNotFoundError(flag_name)
            
            self._flag_users[flag_name].discard(user_id)
            self._log_change(flag_name, "disable_user", {"user_id": user_id}, None)
            return True
    
    def enable_for_organization(self, flag_name: str, organization_id: str) -> bool:
        """
        Enable a feature flag for a specific organization.
        
        Args:
            flag_name: Flag name
            organization_id: Organization ID
            
        Returns:
            True if successful
        """
        with self._lock:
            if flag_name not in self._flags:
                raise FeatureFlagNotFoundError(flag_name)
            
            self._flag_orgs[flag_name].add(organization_id)
            self._log_change(flag_name, "enable_org", None, {"organization_id": organization_id})
            return True
    
    def disable_for_organization(self, flag_name: str, organization_id: str) -> bool:
        """
        Disable a feature flag for a specific organization.
        
        Args:
            flag_name: Flag name
            organization_id: Organization ID
            
        Returns:
            True if successful
        """
        with self._lock:
            if flag_name not in self._flags:
                raise FeatureFlagNotFoundError(flag_name)
            
            self._flag_orgs[flag_name].discard(organization_id)
            self._log_change(flag_name, "disable_org", {"organization_id": organization_id}, None)
            return True
    
    def create_group(self, group_name: str, user_ids: List[str]) -> bool:
        """
        Create a user group for flag targeting.
        
        Args:
            group_name: Group name
            user_ids: List of user IDs in the group
            
        Returns:
            True if successful
        """
        with self._lock:
            self._flag_groups[group_name] = set(user_ids)
            self._log_change("groups", "create", None, {"group_name": group_name, "user_ids": user_ids})
            return True
    
    def enable_for_group(self, flag_name: str, group_name: str) -> bool:
        """
        Enable a feature flag for all users in a group.
        
        Args:
            flag_name: Flag name
            group_name: Group name
            
        Returns:
            True if successful
        """
        with self._lock:
            if flag_name not in self._flags:
                raise FeatureFlagNotFoundError(flag_name)
            if group_name not in self._flag_groups:
                raise ValueError(f"Group '{group_name}' not found")
            
            user_ids = self._flag_groups[group_name]
            for user_id in user_ids:
                self._flag_users[flag_name].add(user_id)
            
            self._log_change(flag_name, "enable_group", None, {"group_name": group_name})
            return True
    
    def _is_in_rollout(self, user_id: str, percentage: float) -> bool:
        """
        Check if a user is in the rollout percentage using consistent hashing.
        
        Args:
            user_id: User ID
            percentage: Rollout percentage (0-100)
            
        Returns:
            True if user is in rollout
        """
        # Create a consistent hash of the user_id
        hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        # Map to 0-100 range
        hash_percent = (hash_val % 10000) / 100.0
        return hash_percent < percentage
    
    def _evaluate_conditions(
        self,
        conditions: Dict[str, Any],
        context: Dict[str, Any],
    ) -> bool:
        """
        Evaluate feature flag conditions against context.
        
        Args:
            conditions: Condition dictionary
            context: Context dictionary
            
        Returns:
            True if conditions are satisfied
        """
        for key, expected_value in conditions.items():
            if key not in context:
                return False
            if context[key] != expected_value:
                return False
        return True
    
    def _log_change(
        self,
        flag_name: str,
        action: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """Log a flag change for audit purposes."""
        self._change_history.append((
            flag_name,
            datetime.utcnow(),
            action,
            old_value,
        ))
        # In production, this would also write to persistent storage
    
    def get_change_history(
        self,
        flag_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Tuple[str, datetime, str, Any]]:
        """
        Get the change history for feature flags.
        
        Args:
            flag_name: Optional flag name to filter by
            limit: Maximum number of entries to return
            
        Returns:
            List of change history entries
        """
        with self._lock:
            history = self._change_history
            if flag_name:
                history = [h for h in history if h[0] == flag_name]
            return history[-limit:]
    
    def statistics(self) -> Dict[str, Any]:
        """Get feature flag manager statistics."""
        with self._lock:
            return {
                "total_flags": len(self._flags),
                "enabled_flags": sum(1 for f in self._flags.values() if f.enabled),
                "flag_users": sum(len(users) for users in self._flag_users.values()),
                "flag_orgs": sum(len(orgs) for orgs in self._flag_orgs.values()),
                "groups": len(self._flag_groups),
                "change_history_count": len(self._change_history),
            }


def get_feature_flag_manager() -> FeatureFlagManager:
    """Get the singleton feature flag manager instance."""
    global _feature_flag_instance
    if _feature_flag_instance is None:
        from datetime import datetime
        _feature_flag_instance = FeatureFlagManager()
    return _feature_flag_instance
