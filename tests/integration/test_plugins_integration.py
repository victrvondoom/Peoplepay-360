"""
Integration tests for the Plugins module.

Tests the complete plugin lifecycle including:
- Plugin registration and discovery
- Capability execution
- Feature flag management
- Configuration validation
- Permission enforcement
"""

import pytest
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from plugins.models import (
    Plugin,
    PluginCapability,
    PluginConfig,
    PluginManifest,
    PluginStatus,
    CapabilityContract,
    CapabilityType,
    ExecutionContext,
    ExecutionResult,
    FeatureFlag,
    PluginDependency,
    PermissionLevel,
)
from plugins.errors import (
    PluginError,
    PluginNotFoundError,
    CapabilityNotFoundError,
    PluginDisabledError,
    CapabilityDisabledError,
    PermissionDeniedError,
    InvalidPluginError,
    InvalidConfigError,
    ExecutionError,
    TimeoutError,
    RetryExhaustedError,
    DependencyError,
    VersionMismatchError,
    FeatureFlagNotFoundError,
    FeatureDisabledError,
)
from plugins.registry import PluginRegistry, get_plugin_registry
from plugins.manager import PluginManager, get_plugin_manager
from plugins.executor import PluginExecutor, get_plugin_executor
from plugins.validator import PluginValidator, get_plugin_validator
from plugins.feature_flags import FeatureFlagManager, get_feature_flag_manager


# Test fixtures
@pytest.fixture
def registry():
    """Get a fresh plugin registry."""
    return PluginRegistry()


@pytest.fixture
def manager(registry):
    """Get a plugin manager with a fresh registry."""
    return PluginManager(registry=registry)


@pytest.fixture
def executor(registry):
    """Get a plugin executor with a fresh registry."""
    return PluginExecutor(registry=registry)


@pytest.fixture
def validator():
    """Get a plugin validator."""
    return PluginValidator()


@pytest.fixture
def feature_flag_manager():
    """Get a feature flag manager."""
    return FeatureFlagManager()


@pytest.fixture
def sample_manifest():
    """Create a sample plugin manifest."""
    return PluginManifest(
        name="test_plugin",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        capabilities=[
            CapabilityContract(
                name="test_capability",
                version="1.0",
                description="A test capability",
                capability_type=CapabilityType.TOOL,
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                timeout_seconds=60,
                max_retries=3,
            ),
        ],
        dependencies=[
            PluginDependency(name="dependency1", version="1.0"),
        ],
    )


@pytest.fixture
def sample_config():
    """Create a sample plugin config."""
    return PluginConfig(
        plugin_name="test_plugin",
        config={"key": "value"},
        enabled=True,
    )


# Registry Tests
class TestPluginRegistry:
    """Test plugin registry functionality."""
    
    def test_register_plugin(self, registry, sample_manifest):
        """Test registering a plugin."""
        plugin = registry.register_plugin(sample_manifest)
        assert plugin is not None
        assert plugin.manifest.name == "test_plugin"
        assert plugin.status == PluginStatus.DISABLED
    
    def test_get_plugin(self, registry, sample_manifest):
        """Test getting a plugin by name."""
        registry.register_plugin(sample_manifest)
        plugin = registry.get_plugin("test_plugin")
        assert plugin is not None
        assert plugin.manifest.name == "test_plugin"
    
    def test_get_plugin_not_found(self, registry):
        """Test getting a non-existent plugin."""
        result = registry.get_plugin("nonexistent")
        assert result is None
    
    def test_unregister_plugin(self, registry, sample_manifest):
        """Test unregistering a plugin."""
        registry.register_plugin(sample_manifest)
        result = registry.unregister_plugin("test_plugin")
        assert result is True
        assert registry.get_plugin("test_plugin") is None
    
    def test_list_plugins(self, registry, sample_manifest):
        """Test listing plugins."""
        registry.register_plugin(sample_manifest)
        plugins = registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0].manifest.name == "test_plugin"
    
    def test_capability_registration(self, registry, sample_manifest):
        """Test that capabilities are registered with plugin."""
        registry.register_plugin(sample_manifest)
        capabilities = registry.list_capabilities()
        assert len(capabilities) == 1
        assert capabilities[0].contract.name == "test_capability"
    
    def test_get_capability(self, registry, sample_manifest):
        """Test getting a capability."""
        registry.register_plugin(sample_manifest)
        capability = registry.get_capability("test_plugin.test_capability")
        assert capability is not None
        assert capability.contract.name == "test_capability"
    
    def test_find_capabilities(self, registry, sample_manifest):
        """Test finding capabilities by query."""
        registry.register_plugin(sample_manifest)
        results = registry.find_capabilities("test")
        assert len(results) == 1
    
    def test_statistics(self, registry, sample_manifest):
        """Test registry statistics."""
        registry.register_plugin(sample_manifest)
        stats = registry.statistics()
        assert stats["plugin_count"] == 1
        assert stats["capability_count"] == 1


# Manager Tests
class TestPluginManager:
    """Test plugin manager functionality."""
    
    def test_load_plugin(self, registry, manager, sample_manifest):
        """Test loading a plugin."""
        registry.register_plugin(sample_manifest)
        plugin = manager.load_plugin("test_plugin")
        assert plugin.status == PluginStatus.LOADED
    
    def test_unload_plugin(self, registry, manager, sample_manifest):
        """Test unloading a plugin."""
        registry.register_plugin(sample_manifest)
        manager.load_plugin("test_plugin")
        result = manager.unload_plugin("test_plugin")
        assert result is True
        plugin = registry.get_plugin("test_plugin")
        assert plugin.status == PluginStatus.DISABLED
    
    def test_enable_disable_plugin(self, registry, manager, sample_manifest):
        """Test enabling and disabling a plugin."""
        registry.register_plugin(sample_manifest)
        plugin = manager.enable_plugin("test_plugin")
        assert plugin.config.enabled is True
        assert plugin.status == PluginStatus.ENABLED
        
        plugin = manager.disable_plugin("test_plugin")
        assert plugin.config.enabled is False
        assert plugin.status == PluginStatus.DISABLED
    
    def test_check_health(self, registry, manager, sample_manifest):
        """Test health checking."""
        registry.register_plugin(sample_manifest)
        result = manager.check_health("test_plugin")
        assert result.healthy is True
        assert result.plugin_name == "test_plugin"
    
    def test_list_loaded_plugins(self, registry, manager, sample_manifest):
        """Test listing loaded plugins."""
        registry.register_plugin(sample_manifest)
        manager.load_plugin("test_plugin")
        loaded = manager.list_loaded_plugins()
        assert len(loaded) == 1
    
    def test_statistics(self, registry, manager, sample_manifest):
        """Test manager statistics."""
        registry.register_plugin(sample_manifest)
        manager.load_plugin("test_plugin")
        stats = manager.statistics()
        assert stats["total_plugins"] == 1
        assert stats["loaded_plugins"] == 1


# Executor Tests
class TestPluginExecutor:
    """Test plugin executor functionality."""
    
    def test_execute_capability(self, registry, executor, sample_manifest):
        """Test executing a capability."""
        registry.register_plugin(sample_manifest)
        manager = PluginManager(registry=registry)
        manager.enable_plugin("test_plugin")
        
        # Get the capability and set implementation
        plugin = registry.get_plugin("test_plugin")
        cap = plugin.capabilities.get("test_capability")
        if cap:
            cap.implementation = lambda x: x + 1
        
        result = executor.execute(
            "test_plugin.test_capability",
            args=(5,),
            caller_id="test_user",
            caller_permissions=[PermissionLevel.READ],
        )
        assert result.success is True
        assert result.result == 6
    
    def test_execute_with_permissions(self, registry, executor, sample_manifest):
        """Test permission enforcement."""
        sample_manifest.capabilities[0].required_permissions = [PermissionLevel.ADMIN]
        sample_manifest.capabilities[0].implementation = lambda: "admin_only"
        registry.register_plugin(sample_manifest)
        manager = PluginManager(registry=registry)
        manager.enable_plugin("test_plugin")
        
        with pytest.raises(PermissionDeniedError):
            executor.execute(
                "test_plugin.test_capability",
                caller_permissions=[PermissionLevel.READ],
            )
    
    def test_execute_disabled_plugin(self, registry, executor, sample_manifest):
        """Test executing from disabled plugin."""
        # Register with disabled config
        config = PluginConfig(
            plugin_name="test_plugin",
            enabled=False,
        )
        registry.register_plugin(sample_manifest, config)
        
        # Get the capability and set implementation
        plugin = registry.get_plugin("test_plugin")
        cap = plugin.capabilities.get("test_capability")
        if cap:
            cap.implementation = lambda: "should_not_run"
        
        with pytest.raises(PluginDisabledError):
            executor.execute("test_plugin.test_capability")
    
    def test_execute_not_found(self, registry, executor):
        """Test executing non-existent capability."""
        with pytest.raises(CapabilityNotFoundError):
            executor.execute("nonexistent.capability")
    
    def test_execute_with_retries(self, registry, executor, sample_manifest):
        """Test retry logic."""
        call_count = [0]
        def failing_then_succeeding():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Not yet")
            return "success"
        
        registry.register_plugin(sample_manifest)
        manager = PluginManager(registry=registry)
        manager.enable_plugin("test_plugin")
        
        # Get the capability and set implementation
        plugin = registry.get_plugin("test_plugin")
        cap = plugin.capabilities.get("test_capability")
        if cap:
            cap.implementation = failing_then_succeeding
            cap.contract.max_retries = 3
        
        result = executor.execute("test_plugin.test_capability")
        assert result.success is True
        assert result.result == "success"
        assert result.retry_count == 2


# Validator Tests
class TestPluginValidator:
    """Test plugin validator functionality."""
    
    def test_validate_manifest(self, validator, sample_manifest):
        """Test manifest validation."""
        is_valid, issues = validator.validate_manifest(sample_manifest)
        assert is_valid is True
        assert len(issues) == 0
    
    def test_validate_invalid_manifest(self, validator):
        """Test validation of invalid manifest."""
        manifest = PluginManifest(
            name="",  # Empty name
            version="",
        )
        is_valid, issues = validator.validate_manifest(manifest)
        assert is_valid is False
        assert len(issues) > 0
    
    def test_validate_capability_contract(self, validator):
        """Test capability contract validation."""
        contract = CapabilityContract(
            name="valid_cap",
            version="1.0",
            timeout_seconds=60,
        )
        issues = validator.validate_capability_contract(contract)
        assert len(issues) == 0
    
    def test_validate_invalid_contract(self, validator):
        """Test validation of invalid contract."""
        contract = CapabilityContract(
            name="",  # Empty name
            version="invalid",
            timeout_seconds=-1,
        )
        issues = validator.validate_capability_contract(contract)
        assert len(issues) > 0
    
    def test_validate_config(self, validator, sample_config):
        """Test config validation."""
        is_valid, issues = validator.validate_config(sample_config)
        assert is_valid is True
    
    def test_check_version_compatibility(self, validator):
        """Test version compatibility checking."""
        assert validator.check_version_compatibility("1.2.3", "1.0") is True
        assert validator.check_version_compatibility("1.0.0", "1.2") is False
        assert validator.check_version_compatibility("2.0.0", "1.0") is True
    
    def test_validate_dependencies(self, validator, sample_manifest):
        """Test dependency validation."""
        available = ["dependency1", "dependency2"]
        is_valid, issues = validator.validate_dependencies(sample_manifest, available)
        assert is_valid is True
    
    def test_validate_missing_dependency(self, validator, sample_manifest):
        """Test validation with missing dependency."""
        available = []
        is_valid, issues = validator.validate_dependencies(sample_manifest, available)
        assert is_valid is False
        assert any("dependency1" in issue for issue in issues)
    
    def test_validate_security(self, validator, sample_manifest):
        """Test security validation."""
        is_secure, warnings = validator.validate_security(sample_manifest)
        assert is_secure is True


# Feature Flag Tests
class TestFeatureFlagManager:
    """Test feature flag manager functionality."""
    
    def test_register_flag(self, feature_flag_manager):
        """Test registering a feature flag."""
        flag = feature_flag_manager.register_flag(
            name="test_flag",
            description="Test feature",
            enabled=True,
        )
        assert flag.name == "test_flag"
        assert flag.enabled is True
    
    def test_get_flag(self, feature_flag_manager):
        """Test getting a feature flag."""
        feature_flag_manager.register_flag(name="test_flag")
        flag = feature_flag_manager.get_flag("test_flag")
        assert flag is not None
        assert flag.name == "test_flag"
    
    def test_get_flag_not_found(self, feature_flag_manager):
        """Test getting non-existent flag."""
        result = feature_flag_manager.get_flag("nonexistent")
        assert result is None
    
    def test_update_flag(self, feature_flag_manager):
        """Test updating a feature flag."""
        feature_flag_manager.register_flag(name="test_flag", enabled=False)
        flag = feature_flag_manager.update_flag("test_flag", enabled=True)
        assert flag.enabled is True
    
    def test_delete_flag(self, feature_flag_manager):
        """Test deleting a feature flag."""
        feature_flag_manager.register_flag(name="test_flag")
        result = feature_flag_manager.delete_flag("test_flag")
        assert result is True
        assert feature_flag_manager.get_flag("test_flag") is None
    
    def test_list_flags(self, feature_flag_manager):
        """Test listing feature flags."""
        feature_flag_manager.register_flag(name="flag1", enabled=True)
        feature_flag_manager.register_flag(name="flag2", enabled=False)
        flags = feature_flag_manager.list_flags()
        assert len(flags) == 2
    
    def test_is_enabled(self, feature_flag_manager):
        """Test checking if a flag is enabled."""
        feature_flag_manager.register_flag(name="test_flag", enabled=True)
        assert feature_flag_manager.is_enabled("test_flag") is True
    
    def test_is_enabled_with_rollout(self, feature_flag_manager):
        """Test rollout percentage."""
        feature_flag_manager.register_flag(
            name="test_flag",
            enabled=True,
            rollout_percentage=50.0,
        )
        # Test with a specific user ID
        # This user should or should not be in the rollout based on consistent hashing
        result = feature_flag_manager.is_enabled("test_flag", user_id="test_user_1")
        assert isinstance(result, bool)
    
    def test_enable_for_user(self, feature_flag_manager):
        """Test enabling for specific user."""
        feature_flag_manager.register_flag(name="test_flag", enabled=False)
        feature_flag_manager.enable_for_user("test_flag", "user1")
        assert feature_flag_manager.is_enabled("test_flag", user_id="user1") is True
        assert feature_flag_manager.is_enabled("test_flag", user_id="user2") is False
    
    def test_enable_for_organization(self, feature_flag_manager):
        """Test enabling for organization."""
        feature_flag_manager.register_flag(name="test_flag", enabled=False)
        feature_flag_manager.enable_for_organization("test_flag", "org1")
        assert feature_flag_manager.is_enabled("test_flag", organization_id="org1") is True
        assert feature_flag_manager.is_enabled("test_flag", organization_id="org2") is False
    
    def test_enable_for_group(self, feature_flag_manager):
        """Test enabling for group."""
        feature_flag_manager.register_flag(name="test_flag", enabled=False)
        feature_flag_manager.create_group("test_group", ["user1", "user2"])
        feature_flag_manager.enable_for_group("test_flag", "test_group")
        assert feature_flag_manager.is_enabled("test_flag", user_id="user1") is True
        assert feature_flag_manager.is_enabled("test_flag", user_id="user3") is False
    
    def test_conditions(self, feature_flag_manager):
        """Test condition-based flag evaluation."""
        feature_flag_manager.register_flag(
            name="test_flag",
            enabled=True,
            conditions={"environment": "production"},
        )
        assert feature_flag_manager.is_enabled("test_flag", context={"environment": "production"}) is True
        assert feature_flag_manager.is_enabled("test_flag", context={"environment": "staging"}) is False
    
    def test_change_history(self, feature_flag_manager):
        """Test change history tracking."""
        feature_flag_manager.register_flag(name="test_flag")
        feature_flag_manager.update_flag("test_flag", enabled=True)
        history = feature_flag_manager.get_change_history("test_flag")
        assert len(history) >= 2  # register + update
    
    def test_statistics(self, feature_flag_manager):
        """Test statistics."""
        feature_flag_manager.register_flag(name="flag1", enabled=True)
        feature_flag_manager.register_flag(name="flag2", enabled=False)
        stats = feature_flag_manager.statistics()
        assert stats["total_flags"] == 2
        assert stats["enabled_flags"] == 1


# Singleton Tests
class TestSingletons:
    """Test singleton pattern for all managers."""
    
    def test_registry_singleton(self):
        """Test plugin registry singleton."""
        registry1 = get_plugin_registry()
        registry2 = get_plugin_registry()
        assert registry1 is registry2
    
    def test_manager_singleton(self):
        """Test plugin manager singleton."""
        manager1 = get_plugin_manager()
        manager2 = get_plugin_manager()
        assert manager1 is manager2
    
    def test_executor_singleton(self):
        """Test plugin executor singleton."""
        executor1 = get_plugin_executor()
        executor2 = get_plugin_executor()
        assert executor1 is executor2
    
    def test_validator_singleton(self):
        """Test plugin validator singleton."""
        validator1 = get_plugin_validator()
        validator2 = get_plugin_validator()
        assert validator1 is validator2
    
    def test_feature_flag_manager_singleton(self):
        """Test feature flag manager singleton."""
        ffm1 = get_feature_flag_manager()
        ffm2 = get_feature_flag_manager()
        assert ffm1 is ffm2


# Error Tests
class TestErrors:
    """Test error classes."""
    
    def test_plugin_error(self):
        """Test PluginError."""
        error = PluginError("Test error")
        assert error.message == "Test error"
        assert error.error_type == "plugin_error"
    
    def test_plugin_not_found_error(self):
        """Test PluginNotFoundError."""
        error = PluginNotFoundError("test_plugin")
        assert error.plugin_name == "test_plugin"
    
    def test_capability_not_found_error(self):
        """Test CapabilityNotFoundError."""
        error = CapabilityNotFoundError("test_cap")
        assert error.capability_name == "test_cap"
    
    def test_permission_denied_error(self):
        """Test PermissionDeniedError."""
        error = PermissionDeniedError("No permission")
        assert error.message == "No permission"
    
    def test_invalid_plugin_error(self):
        """Test InvalidPluginError."""
        error = InvalidPluginError("test_plugin", issues=["issue1"])
        assert error.plugin_name == "test_plugin"
        assert len(error.issues) == 1
    
    def test_to_dict(self):
        """Test error to_dict method."""
        error = PluginError("Test", details={"key": "value"})
        result = error.to_dict()
        assert result["error"] == "plugin_error"
        assert result["message"] == "Test"
        assert result["details"] == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
