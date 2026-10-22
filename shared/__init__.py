"""PeoplePay 360 - Shared Infrastructure Package

This package contains shared contracts, schemas, utilities, and infrastructure
that are used across all PeoplePay 360 services.

Components:
- schemas.py: Common data contracts (User, Organization, Permission, etc.)
- errors.py: Standard error schemas and exception handling
- config.py: Centralized configuration management
- logging.py: Structured logging utilities
- auth.py: Authentication and authorization utilities
- types.py: Common type definitions
"""

from shared.schemas import (
    User,
    Organization,
    Permission,
    UserRole,
    AuditEvent,
    ErrorResponse,
    HealthResponse,
    PaginatedResponse,
)
from shared.errors import (
    PeoplePayError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    NotFoundError,
    ConflictError,
)
from shared.config import (
    Config,
    get_config,
    ServiceConfig,
)
from shared.logging_wrapper import (
    get_logger,
    setup_logging,
    LogContext,
)

__all__ = [
    # Schemas
    "User",
    "Organization",
    "Permission",
    "UserRole",
    "AuditEvent",
    "ErrorResponse",
    "HealthResponse",
    "PaginatedResponse",
    # Errors
    "PeoplePayError",
    "AuthenticationError",
    "AuthorizationError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    # Config
    "Config",
    "get_config",
    "ServiceConfig",
    # Logging
    "get_logger",
    "setup_logging",
    "LogContext",
]
