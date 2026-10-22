"""
Plugin Validator

Validates plugin manifests, configurations, and capability contracts.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from plugins.models import (
    PluginManifest,
    PluginConfig,
    CapabilityContract,
    PluginDependency,
)
from plugins.errors import (
    InvalidPluginError,
    InvalidConfigError,
    VersionMismatchError,
    DependencyError,
)


# Singleton instance
_validator_instance: Optional["PluginValidator"] = None


class PluginValidator:
    """
    Validates plugin manifests, configurations, and capability contracts.
    
    Provides:
    - Manifest validation
    - Configuration validation
    - Capability contract validation
    - Dependency validation
    - Version compatibility checking
    - Security validation
    """
    
    def __init__(self):
        """Initialize the plugin validator."""
        self._name_pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
        self._version_pattern = re.compile(r"^\d+\.\d+(\.\d+)?$")
        self._semver_pattern = re.compile(r"^\d+\.\d+\.\d+$")
    
    def validate_manifest(self, manifest: PluginManifest) -> Tuple[bool, List[str]]:
        """
        Validate a plugin manifest.
        
        Args:
            manifest: Plugin manifest to validate
            
        Returns:
            Tuple of (is_valid, list of issues)
        """
        issues: List[str] = []
        
        # Validate name
        if not manifest.name:
            issues.append("Plugin name is required")
        elif not self._name_pattern.match(manifest.name):
            issues.append(f"Invalid plugin name: '{manifest.name}'. Must start with letter and contain only alphanumeric, underscore, or hyphen.")
        
        # Validate version
        if not manifest.version:
            issues.append("Plugin version is required")
        elif not self._version_pattern.match(manifest.version):
            issues.append(f"Invalid version format: '{manifest.version}'. Must be X.Y or X.Y.Z format.")
        
        # Validate description
        if not manifest.description:
            issues.append("Plugin description is required")
        
        # Validate author
        if not manifest.author:
            issues.append("Plugin author is required")
        
        # Validate capabilities
        for cap in manifest.capabilities:
            cap_issues = self.validate_capability_contract(cap)
            for issue in cap_issues:
                issues.append(f"Capability '{cap.name}': {issue}")
        
        # Validate dependencies
        for dep in manifest.dependencies:
            dep_issues = self.validate_dependency(dep)
            for issue in dep_issues:
                issues.append(f"Dependency '{dep.name}': {issue}")
        
        # Validate Python version requirement
        if manifest.python_version and not self._validate_python_version(manifest.python_version):
            issues.append(f"Invalid Python version requirement: '{manifest.python_version}'")
        
        return len(issues) == 0, issues
    
    def validate_capability_contract(self, contract: CapabilityContract) -> List[str]:
        """
        Validate a capability contract.
        
        Args:
            contract: Capability contract to validate
            
        Returns:
            List of issues
        """
        issues: List[str] = []
        
        # Validate name
        if not contract.name:
            issues.append("Capability name is required")
        elif not self._name_pattern.match(contract.name):
            issues.append(f"Invalid capability name: '{contract.name}'")
        
        # Validate version
        if not contract.version:
            issues.append("Capability version is required")
        elif not self._version_pattern.match(contract.version):
            issues.append(f"Invalid version format: '{contract.version}'")
        
        # Validate timeout
        if contract.timeout_seconds < 1:
            issues.append(f"Timeout must be at least 1 second, got {contract.timeout_seconds}")
        
        # Validate max retries
        if contract.max_retries < 0:
            issues.append(f"Max retries must be non-negative, got {contract.max_retries}")
        
        # Validate max execution time
        if contract.max_execution_time_seconds < 1:
            issues.append(f"Max execution time must be at least 1 second, got {contract.max_execution_time_seconds}")
        
        return issues
    
    def validate_dependency(self, dependency: PluginDependency) -> List[str]:
        """
        Validate a plugin dependency.
        
        Args:
            dependency: Plugin dependency to validate
            
        Returns:
            List of issues
        """
        issues: List[str] = []
        
        if not dependency.name:
            issues.append("Dependency name is required")
        elif not self._name_pattern.match(dependency.name):
            issues.append(f"Invalid dependency name: '{dependency.name}'")
        
        # Validate version constraints
        if dependency.version != "*":
            if not self._version_pattern.match(dependency.version):
                issues.append(f"Invalid dependency version: '{dependency.version}'")
        
        if dependency.minimum_version and not self._version_pattern.match(dependency.minimum_version):
            issues.append(f"Invalid minimum version: '{dependency.minimum_version}'")
        
        if dependency.maximum_version and not self._version_pattern.match(dependency.maximum_version):
            issues.append(f"Invalid maximum version: '{dependency.maximum_version}'")
        
        return issues
    
    def validate_config(
        self,
        config: PluginConfig,
        manifest: Optional[PluginManifest] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Validate plugin configuration.
        
        Args:
            config: Plugin configuration to validate
            manifest: Optional manifest for schema validation
            
        Returns:
            Tuple of (is_valid, list of issues)
        """
        issues: List[str] = []
        
        # Validate plugin name
        if not config.plugin_name:
            issues.append("Plugin name is required in configuration")
        
        # Validate config structure if schema is provided
        if manifest and manifest.config_schema:
            schema_issues = self._validate_against_schema(
                config.config,
                manifest.config_schema,
            )
            for issue in schema_issues:
                issues.append(f"Config schema: {issue}")
        
        # Validate timeout override
        if config.timeout_override is not None and config.timeout_override < 1:
            issues.append(f"Timeout override must be at least 1 second, got {config.timeout_override}")
        
        # Validate max retries override
        if config.max_retries is not None and config.max_retries < 0:
            issues.append(f"Max retries override must be non-negative, got {config.max_retries}")
        
        return len(issues) == 0, issues
    
    def validate_dependencies(
        self,
        manifest: PluginManifest,
        available_plugins: List[str],
    ) -> Tuple[bool, List[str]]:
        """
        Validate that all dependencies are available.
        
        Args:
            manifest: Plugin manifest
            available_plugins: List of available plugin names
            
        Returns:
            Tuple of (all_satisfied, list of issues)
        """
        issues: List[str] = []
        available_set = set(available_plugins)
        
        for dep in manifest.dependencies:
            if dep.name not in available_set:
                if dep.optional:
                    issues.append(f"Optional dependency '{dep.name}' not available (will be skipped)")
                else:
                    issues.append(f"Required dependency '{dep.name}' not available")
            else:
                # Check version constraints
                version_issues = self._check_version_constraints(
                    dep,
                    available_set,
                )
                for issue in version_issues:
                    issues.append(issue)
        
        return len(issues) == 0, issues
    
    def check_version_compatibility(
        self,
        plugin_version: str,
        required_version: str,
    ) -> bool:
        """
        Check if a plugin version satisfies a requirement.
        
        Args:
            plugin_version: Available version
            required_version: Required version (e.g., ">=1.0", "1.2.3")
            
        Returns:
            True if compatible
        """
        try:
            # Simple exact match
            if plugin_version == required_version:
                return True
            
            # Simple >= comparison (major.minor)
            plugin_parts = self._parse_version(plugin_version)
            required_parts = self._parse_version(required_version)
            
            for i in range(min(len(plugin_parts), len(required_parts))):
                if plugin_parts[i] < required_parts[i]:
                    return False
                elif plugin_parts[i] > required_parts[i]:
                    return True
            
            return True
        except (ValueError, IndexError):
            return False
    
    def _parse_version(self, version: str) -> List[int]:
        """Parse version string into numeric parts."""
        return [int(part) for part in version.split(".") if part.isdigit()]
    
    def _validate_python_version(self, version: str) -> bool:
        """Validate Python version requirement."""
        # Accept formats like ">=3.8", "3.8", ">3.7", "==3.9"
        pattern = re.compile(r"^(>=|<=|>|<|=|==)\s*\d+\.\d+")
        return bool(pattern.match(version))
    
    def _validate_against_schema(
        self,
        config: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> List[str]:
        """Validate configuration against a schema."""
        issues: List[str] = []
        
        # Check required fields
        if "required" in schema:
            for field in schema["required"]:
                if field not in config:
                    issues.append(f"Missing required field: '{field}'")
        
        # Check field types
        if "properties" in schema:
            for field, field_schema in schema["properties"].items():
                if field in config:
                    expected_type = field_schema.get("type")
                    if expected_type:
                        actual_type = type(config[field]).__name__
                        if expected_type != actual_type:
                            issues.append(
                                f"Field '{field}' has type '{actual_type}', expected '{expected_type}'"
                            )
        
        return issues
    
    def _check_version_constraints(
        self,
        dependency: PluginDependency,
        available_plugins: set,
    ) -> List[str]:
        """Check version constraints for a dependency."""
        issues: List[str] = []
        
        # In a real implementation, we would look up the actual version
        # For now, just check that the dependency exists
        if dependency.name not in available_plugins:
            return issues
        
        return issues
    
    def validate_security(
        self,
        manifest: PluginManifest,
    ) -> Tuple[bool, List[str]]:
        """
        Validate security aspects of a plugin.
        
        Args:
            manifest: Plugin manifest
            
        Returns:
            Tuple of (is_secure, list of warnings)
        """
        warnings: List[str] = []
        
        # Check for suspicious patterns in capabilities
        for cap in manifest.capabilities:
            if not cap.is_safe:
                warnings.append(f"Capability '{cap.name}' is marked as unsafe")
        
        # Check for excessive permissions
        for cap in manifest.capabilities:
            if any(p in ["SYSTEM", "ADMIN"] for p in cap.required_permissions):
                warnings.append(f"Capability '{cap.name}' requires elevated permissions")
        
        return len(warnings) == 0, warnings
    
    def statistics(self) -> Dict[str, Any]:
        """Get validator statistics."""
        return {
            "validations_performed": 0,  # Would be tracked in production
        }


def get_plugin_validator() -> PluginValidator:
    """Get the singleton plugin validator instance."""
    global _validator_instance
    if _validator_instance is None:
        from datetime import datetime
        _validator_instance = PluginValidator()
    return _validator_instance
