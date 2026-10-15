"""Permission management and RBAC."""

from __future__ import annotations

import fnmatch
import logging
from functools import wraps
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from auth.models import User, Permission, Role, OrganizationMembership
    from auth.errors import AuthorizationError, PermissionDeniedError


logger = logging.getLogger(__name__)


class PermissionManager:
    """Manages permissions and role-based access control."""
    
    def __init__(
        self,
        default_permissions: dict[str, Permission] | None = None,
        default_roles: dict[str, Role] | None = None,
    ):
        """Initialize the permission manager.
        
        Args:
            default_permissions: Dictionary of default permissions
            default_roles: Dictionary of default roles
        """
        from auth.models import Permission, Role
        
        self._permissions: dict[str, Permission] = default_permissions or {}
        self._roles: dict[str, Role] = default_roles or {}
        
        # Add default permissions and roles
        if not self._permissions:
            self._permissions = Permission.default_permissions()
        if not self._roles:
            self._roles = Role.default_roles()
    
    def register_permission(self, permission: "Permission") -> None:
        """Register a new permission.
        
        Args:
            permission: The permission to register
        """
        self._permissions[permission.code] = permission
    
    def get_permission(self, code: str) -> "Permission | None":
        """Get a permission by code.
        
        Args:
            code: The permission code
            
        Returns:
            The permission or None
        """
        return self._permissions.get(code)
    
    def list_permissions(self) -> list["Permission"]:
        """List all registered permissions."""
        return list(self._permissions.values())
    
    def register_role(self, role: "Role") -> None:
        """Register a new role.
        
        Args:
            role: The role to register
        """
        self._roles[role.role_id] = role
    
    def get_role(self, role_id: str) -> "Role | None":
        """Get a role by ID.
        
        Args:
            role_id: The role identifier
            
        Returns:
            The role or None
        """
        return self._roles.get(role_id)
    
    def list_roles(self) -> list["Role"]:
        """List all registered roles."""
        return list(self._roles.values())
    
    def has_permission(
        self,
        user: "User | None",
        permission_code: str,
        organization_id: str | None = None,
        resource_id: str | None = None,
    ) -> bool:
        """Check if a user has a specific permission.
        
        Args:
            user: The user to check
            permission_code: The permission code
            organization_id: Optional organization context
            resource_id: Optional resource identifier
            
        Returns:
            True if user has permission, False otherwise
        """
        if user is None:
            return False
        
        # Check if user has wildcard permission
        user_perms = getattr(user, 'permissions', [])
        if "*" in user_perms:
            return True
        
        # Check user-level permissions
        if permission_code in user_perms:
            return True
        
        # Check organization-level permissions
        if organization_id:
            # This would check organization memberships in a real implementation
            # For now, we'll use a simplified approach
            org_perms = self._get_organization_permissions(user, organization_id)
            if permission_code in org_perms:
                return True
            if "*" in org_perms:
                return True
        
        # Check role-based permissions
        if self._check_role_permissions(user, permission_code, organization_id):
            return True
        
        return False
    
    def check_permission(
        self,
        user: "User | None",
        permission_code: str,
        organization_id: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        """Check permission and raise error if not authorized.
        
        Args:
            user: The user to check
            permission_code: The permission code
            organization_id: Optional organization context
            resource_id: Optional resource identifier
            
        Raises:
            PermissionDeniedError: If user doesn't have permission
        """
        from auth.errors import PermissionDeniedError
        
        if not self.has_permission(user, permission_code, organization_id, resource_id):
            user_id = getattr(user, 'user_id', None) if user else None
            raise PermissionDeniedError(
                permission=permission_code,
                user_id=user_id,
                resource_id=resource_id,
            )
    
    def require_permission(
        self,
        permission_code: str,
        organization_id: str | None = None,
    ) -> Callable:
        """Decorator to require a permission for a function.
        
        Args:
            permission_code: The required permission code
            organization_id: Optional organization context
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                # Extract user from context or arguments
                user = self._extract_user_from_context(args, kwargs)
                
                if user is None:
                    # User might be in kwargs
                    user = kwargs.get('user')
                
                self.check_permission(user, permission_code, organization_id)
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def require_any_permission(
        self,
        permission_codes: list[str],
        organization_id: str | None = None,
    ) -> Callable:
        """Decorator to require any of the specified permissions.
        
        Args:
            permission_codes: List of permission codes (any one required)
            organization_id: Optional organization context
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                user = self._extract_user_from_context(args, kwargs)
                if user is None:
                    user = kwargs.get('user')
                
                if user is None:
                    raise PermissionDeniedError(
                        permission=", ".join(permission_codes),
                        user_id=None,
                    )
                
                # Check if user has any of the required permissions
                for code in permission_codes:
                    if self.has_permission(user, code, organization_id):
                        return func(*args, **kwargs)
                
                raise PermissionDeniedError(
                    permission=", ".join(permission_codes),
                    user_id=getattr(user, 'user_id', None),
                )
            return wrapper
        return decorator
    
    def require_all_permissions(
        self,
        permission_codes: list[str],
        organization_id: str | None = None,
    ) -> Callable:
        """Decorator to require all of the specified permissions.
        
        Args:
            permission_codes: List of permission codes (all required)
            organization_id: Optional organization context
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                user = self._extract_user_from_context(args, kwargs)
                if user is None:
                    user = kwargs.get('user')
                
                if user is None:
                    raise PermissionDeniedError(
                        permission=", ".join(permission_codes),
                        user_id=None,
                    )
                
                # Check if user has all required permissions
                for code in permission_codes:
                    if not self.has_permission(user, code, organization_id):
                        raise PermissionDeniedError(
                            permission=code,
                            user_id=getattr(user, 'user_id', None),
                        )
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def can_access_resource(
        self,
        user: "User | None",
        resource_type: str,
        resource_id: str,
        permission: str = "read",
        organization_id: str | None = None,
    ) -> bool:
        """Check if user can access a specific resource.
        
        Args:
            user: The user to check
            resource_type: The resource type
            resource_id: The resource identifier
            permission: The permission level (read, write, delete, admin)
            organization_id: Optional organization context
            
        Returns:
            True if access is allowed, False otherwise
        """
        # In a real implementation, this would check resource ownership,
        # organization memberships, and specific resource permissions
        
        # For now, we'll use a simplified approach
        permission_code = f"{resource_type}:{permission}"
        return self.has_permission(user, permission_code, organization_id)
    
    def get_user_permissions(
        self,
        user: "User | None",
        organization_id: str | None = None,
    ) -> list[str]:
        """Get all permissions for a user.
        
        Args:
            user: The user
            organization_id: Optional organization context
            
        Returns:
            List of permission codes
        """
        if user is None:
            return []
        
        perms = set(getattr(user, 'permissions', []))
        
        # Add organization permissions
        if organization_id:
            org_perms = self._get_organization_permissions(user, organization_id)
            perms.update(org_perms)
        
        return list(perms)
    
    def _extract_user_from_context(self, args: tuple, kwargs: dict) -> Any:
        """Extract user from function arguments."""
        # Try to get user from various positions
        if args:
            # First arg might be user
            if hasattr(args[0], 'user_id'):
                return args[0]
        
        # Try kwargs
        return kwargs.get('user')
    
    def _get_organization_permissions(
        self,
        user: "User",
        organization_id: str,
    ) -> set[str]:
        """Get organization-level permissions for a user."""
        # In a real implementation, this would query the database
        # For now, we'll return an empty set
        return set()
    
    def _check_role_permissions(
        self,
        user: "User",
        permission_code: str,
        organization_id: str | None,
    ) -> bool:
        """Check role-based permissions for a user."""
        # In a real implementation, this would check user roles
        # For now, we'll return False
        return False


# =============================================================================
# MODULE-LEVEL FUNCTIONS
# =============================================================================

# Global permission manager instance
_permission_manager: PermissionManager | None = None


def get_permission_manager() -> PermissionManager:
    """Get the global permission manager."""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager


def has_permission(
    user: "User | None",
    permission_code: str,
    organization_id: str | None = None,
    resource_id: str | None = None,
) -> bool:
    """Check if user has a permission.
    
    Args:
        user: The user
        permission_code: The permission code
        organization_id: Optional organization context
        resource_id: Optional resource identifier
        
    Returns:
        True if user has permission
    """
    return get_permission_manager().has_permission(
        user, permission_code, organization_id, resource_id
    )


def check_permission(
    user: "User | None",
    permission_code: str,
    organization_id: str | None = None,
    resource_id: str | None = None,
) -> None:
    """Check permission and raise error if not authorized.
    
    Args:
        user: The user
        permission_code: The permission code
        organization_id: Optional organization context
        resource_id: Optional resource identifier
        
    Raises:
        PermissionDeniedError: If user doesn't have permission
    """
    get_permission_manager().check_permission(
        user, permission_code, organization_id, resource_id
    )


def require_permission(
    permission_code: str,
    organization_id: str | None = None,
) -> Callable:
    """Decorator to require a permission.
    
    Args:
        permission_code: The required permission code
        organization_id: Optional organization context
        
    Returns:
        Decorator function
    """
    return get_permission_manager().require_permission(
        permission_code, organization_id
    )


def reset_permission_manager() -> None:
    """Reset the global permission manager (for testing)."""
    global _permission_manager
    _permission_manager = None
