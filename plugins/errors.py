"""
Plugin and Integration Error Definitions
"""

from typing import Any, Dict, List, Optional


class PluginError(Exception):
    """Base exception for plugin-related errors."""
    
    def __init__(self, message: str, error_type: str = "plugin_error", details: Optional[Dict[str, Any]] = None):
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


class PluginNotFoundError(PluginError):
    """Raised when a plugin cannot be found."""
    
    def __init__(self, plugin_name: str, message: Optional[str] = None):
        self.plugin_name = plugin_name
        msg = message or f"Plugin '{plugin_name}' not found"
        super().__init__(msg, error_type="plugin_not_found", details={"plugin_name": plugin_name})


class CapabilityNotFoundError(PluginError):
    """Raised when a capability cannot be found."""
    
    def __init__(self, capability_name: str, plugin_name: Optional[str] = None, message: Optional[str] = None):
        self.capability_name = capability_name
        self.plugin_name = plugin_name
        msg = message or f"Capability '{capability_name}' not found"
        super().__init__(
            msg,
            error_type="capability_not_found",
            details={"capability_name": capability_name, "plugin_name": plugin_name}
        )


class PluginDisabledError(PluginError):
    """Raised when a plugin is disabled."""
    
    def __init__(self, plugin_name: str, message: Optional[str] = None):
        self.plugin_name = plugin_name
        msg = message or f"Plugin '{plugin_name}' is disabled"
        super().__init__(msg, error_type="plugin_disabled", details={"plugin_name": plugin_name})


class CapabilityDisabledError(PluginError):
    """Raised when a capability is disabled."""
    
    def __init__(self, capability_name: str, plugin_name: Optional[str] = None, message: Optional[str] = None):
        self.capability_name = capability_name
        self.plugin_name = plugin_name
        msg = message or f"Capability '{capability_name}' is disabled"
        super().__init__(
            msg,
            error_type="capability_disabled",
            details={"capability_name": capability_name, "plugin_name": plugin_name}
        )


class PermissionDeniedError(PluginError):
    """Raised when permission is denied."""
    
    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, error_type="permission_denied", details=details or {})


class InvalidPluginError(PluginError):
    """Raised when a plugin is invalid."""
    
    def __init__(self, plugin_name: str, message: Optional[str] = None, issues: Optional[List[str]] = None):
        self.plugin_name = plugin_name
        self.issues = issues or []
        msg = message or f"Plugin '{plugin_name}' is invalid: {', '.join(self.issues[:3])}"
        super().__init__(
            msg,
            error_type="invalid_plugin",
            details={"plugin_name": plugin_name, "issues": self.issues}
        )


class InvalidConfigError(PluginError):
    """Raised when plugin configuration is invalid."""
    
    def __init__(self, plugin_name: str, message: Optional[str] = None, issues: Optional[List[str]] = None):
        self.plugin_name = plugin_name
        self.issues = issues or []
        msg = message or f"Invalid configuration for plugin '{plugin_name}'"
        super().__init__(
            msg,
            error_type="invalid_config",
            details={"plugin_name": plugin_name, "issues": self.issues}
        )


class ExecutionError(PluginError):
    """Raised when plugin execution fails."""
    
    def __init__(
        self,
        plugin_name: str,
        capability_name: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.plugin_name = plugin_name
        self.capability_name = capability_name
        super().__init__(
            message,
            error_type="execution_error",
            details={
                "plugin_name": plugin_name,
                "capability_name": capability_name,
                **(details or {})
            }
        )


class TimeoutError(PluginError):
    """Raised when plugin execution times out."""
    
    def __init__(
        self,
        plugin_name: str,
        capability_name: str,
        timeout: int,
        message: Optional[str] = None,
    ):
        self.plugin_name = plugin_name
        self.capability_name = capability_name
        self.timeout = timeout
        msg = message or f"Execution of '{plugin_name}.{capability_name}' timed out after {timeout}s"
        super().__init__(
            msg,
            error_type="timeout_error",
            details={
                "plugin_name": plugin_name,
                "capability_name": capability_name,
                "timeout": timeout,
            }
        )


class RetryExhaustedError(PluginError):
    """Raised when all retries have been exhausted."""
    
    def __init__(
        self,
        plugin_name: str,
        capability_name: str,
        retries: int,
        message: Optional[str] = None,
    ):
        self.plugin_name = plugin_name
        self.capability_name = capability_name
        self.retries = retries
        msg = message or f"All {retries} retries exhausted for '{plugin_name}.{capability_name}'"
        super().__init__(
            msg,
            error_type="retry_exhausted",
            details={
                "plugin_name": plugin_name,
                "capability_name": capability_name,
                "retries": retries,
            }
        )


class DependencyError(PluginError):
    """Raised when a plugin dependency is not satisfied."""
    
    def __init__(self, plugin_name: str, dependency_name: str, message: Optional[str] = None):
        self.plugin_name = plugin_name
        self.dependency_name = dependency_name
        msg = message or f"Dependency '{dependency_name}' not satisfied for plugin '{plugin_name}'"
        super().__init__(
            msg,
            error_type="dependency_error",
            details={
                "plugin_name": plugin_name,
                "dependency_name": dependency_name,
            }
        )


class VersionMismatchError(PluginError):
    """Raised when plugin version requirements are not met."""
    
    def __init__(
        self,
        plugin_name: str,
        required_version: str,
        available_version: str,
        message: Optional[str] = None,
    ):
        self.plugin_name = plugin_name
        self.required_version = required_version
        self.available_version = available_version
        msg = message or f"Version mismatch for plugin '{plugin_name}': requires {required_version}, has {available_version}"
        super().__init__(
            msg,
            error_type="version_mismatch",
            details={
                "plugin_name": plugin_name,
                "required_version": required_version,
                "available_version": available_version,
            }
        )


class FeatureFlagNotFoundError(PluginError):
    """Raised when a feature flag cannot be found."""
    
    def __init__(self, flag_name: str, message: Optional[str] = None):
        self.flag_name = flag_name
        msg = message or f"Feature flag '{flag_name}' not found"
        super().__init__(msg, error_type="feature_flag_not_found", details={"flag_name": flag_name})


class FeatureDisabledError(PluginError):
    """Raised when a feature is disabled."""
    
    def __init__(self, flag_name: str, message: Optional[str] = None):
        self.flag_name = flag_name
        msg = message or f"Feature '{flag_name}' is disabled"
        super().__init__(msg, error_type="feature_disabled", details={"flag_name": flag_name})


# Ensure all error types are available
PluginException = PluginError
CapabilityException = CapabilityNotFoundError
