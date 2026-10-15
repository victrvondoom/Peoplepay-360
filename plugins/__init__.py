"""
PeoplePay 360 - Integration and Plugin Architecture

This module provides a stable internal integration framework supporting:
- Versioned plugin contracts
- Capability registry
- Plugin lifecycle management
- Feature flags
- Permissions and scopes
- Configuration validation
- Adapter contracts
- Health checks
- Compatibility testing
- Secure tool execution
- Failure isolation
- Retry control
- Cancellation support
- Dependency declarations
- Disabled/unavailable status
- Audit logging

Future integrations can be added without restructuring the core business logic.
Plugins must never grant themselves unrestricted access.
"""

from plugins.models import (
    Plugin,
    PluginCapability,
    PluginConfig,
    PluginManifest,
    PluginStatus,
    CapabilityContract,
    CapabilityType,
    ExecutionMode,
    FeatureFlag,
    PluginDependency,
    ExecutionContext,
    ExecutionResult,
    PermissionLevel,
    HealthCheckResult,
)
from plugins.registry import PluginRegistry, get_plugin_registry
from plugins.manager import PluginManager, get_plugin_manager
from plugins.executor import PluginExecutor, get_plugin_executor
from plugins.validator import PluginValidator, get_plugin_validator
from plugins.feature_flags import FeatureFlagManager, get_feature_flag_manager
from plugins.errors import (
    PluginError,
    PluginNotFoundError,
    CapabilityNotFoundError,
    PluginDisabledError,
    PermissionDeniedError,
    InvalidPluginError,
    ExecutionError,
    DependencyError,
)

__all__ = [
    # Models
    "Plugin",
    "PluginCapability",
    "PluginConfig",
    "PluginManifest",
    "PluginStatus",
    "CapabilityContract",
    "CapabilityType",
    "ExecutionMode",
    "FeatureFlag",
    "PluginDependency",
    "ExecutionContext",
    "ExecutionResult",
    "PermissionLevel",
    "HealthCheckResult",
    # Services
    "PluginRegistry",
    "get_plugin_registry",
    "PluginManager",
    "get_plugin_manager",
    "PluginExecutor",
    "get_plugin_executor",
    "PluginValidator",
    "get_plugin_validator",
    "FeatureFlagManager",
    "get_feature_flag_manager",
    # Errors
    "PluginError",
    "PluginNotFoundError",
    "CapabilityNotFoundError",
    "PluginDisabledError",
    "PermissionDeniedError",
    "InvalidPluginError",
    "ExecutionError",
    "DependencyError",
]
