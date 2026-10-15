"""PeoplePay 360 - Authentication and Authorization Service

This module provides centralized authentication, authorization, and identity
management for all PeoplePay 360 services.

Components:
- auth_manager.py: Main authentication manager with token handling
- permission.py: Permission management and RBAC
- session.py: Session management
- password.py: Password hashing and verification
- mfa.py: Multi-factor authentication utilities
- models.py: Data models for users, organizations, roles
"""

from auth.auth_manager import AuthManager, get_auth_manager
from auth.permission import (
    PermissionManager,
    has_permission,
    check_permission,
    require_permission,
)
from auth.session import SessionManager
from auth.password import PasswordHasher
from auth.models import (
    User,
    Organization,
    Role,
    Permission,
    Session as AuthSession,
)
from auth.errors import (
    AuthError,
    AuthenticationError,
    AuthorizationError,
    SessionError,
    PermissionDeniedError,
    InvalidCredentialsError,
    UserNotFoundError,
    UserAlreadyExistsError,
    SessionExpiredError,
    SessionInvalidError,
)

__all__ = [
    # Auth Manager
    "AuthManager",
    "get_auth_manager",
    # Permission
    "PermissionManager",
    "has_permission",
    "check_permission",
    "require_permission",
    # Session
    "SessionManager",
    # Password
    "PasswordHasher",
    # Models
    "User",
    "Organization",
    "Role",
    "Permission",
    # Errors
    "AuthError",
    "AuthenticationError",
    "AuthorizationError",
    "SessionError",
    "PermissionDeniedError",
    "InvalidCredentialsError",
    "UserNotFoundError",
    "UserAlreadyExistsError",
    "SessionExpiredError",
    "SessionInvalidError",
]
