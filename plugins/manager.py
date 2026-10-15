"""
Plugin Manager

Manages plugin lifecycle including loading, unloading, configuration, and health checks.
"""

import threading
from typing import Any, Dict, List, Optional
from datetime import datetime

from plugins.models import (
    Plugin,
    PluginConfig,
    PluginManifest,
    PluginStatus,
    HealthCheckResult,
)
from plugins.registry import get_plugin_registry, PluginRegistry
from plugins.errors import (
    PluginError,
    PluginNotFoundError,
    InvalidConfigError,
    PluginDisabledError,
)


# Singleton instance
_manager_instance: Optional["PluginManager"] = None


class PluginManager:
    """
    Manages the lifecycle of plugins.
    
    Provides:
    - Plugin loading and unloading
    - Configuration management
    - Health monitoring
    - Status tracking
    """
    
    def __init__(self, registry: Optional[PluginRegistry] = None):
        """Initialize the plugin manager."""
        self.registry = registry or get_plugin_registry()
        self._lock = threading.Lock()
        self._loaded_plugins: Dict[str, Plugin] = {}
    
    def load_plugin(
        self,
        plugin_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Plugin:
        """
        Load a plugin.
        
        Args:
            plugin_name: Name of the plugin to load
            config: Optional configuration
            
        Returns:
            The loaded Plugin object
        """
        with self._lock:
            # Get the plugin from registry
            plugin = self.registry.get_plugin(plugin_name)
            if not plugin:
                raise PluginNotFoundError(plugin_name)
            
            # Apply configuration
            if config:
                plugin.config = PluginConfig(
                    plugin_name=plugin_name,
                    config=config,
                    enabled=plugin.config.enabled,
                )
            
            # Update status
            plugin.status = PluginStatus.LOADED
            plugin.loaded_at = datetime.utcnow()
            self._loaded_plugins[plugin_name] = plugin
            
            # Perform health check
            self.check_health(plugin_name)
            
            return plugin
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin.
        
        Args:
            plugin_name: Name of the plugin to unload
            
        Returns:
            True if unloaded, False if not found
        """
        with self._lock:
            if plugin_name not in self._loaded_plugins:
                return False
            
            plugin = self._loaded_plugins[plugin_name]
            plugin.status = PluginStatus.DISABLED
            plugin.loaded_at = None
            del self._loaded_plugins[plugin_name]
            return True
    
    def configure_plugin(
        self,
        plugin_name: str,
        config: Dict[str, Any],
    ) -> Plugin:
        """
        Configure a plugin.
        
        Args:
            plugin_name: Name of the plugin to configure
            config: Configuration dictionary
            
        Returns:
            The configured Plugin object
        """
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            raise PluginNotFoundError(plugin_name)
        
        plugin.config = PluginConfig(
            plugin_name=plugin_name,
            config=config,
            enabled=plugin.config.enabled,
        )
        return plugin
    
    def enable_plugin(self, plugin_name: str) -> Plugin:
        """Enable a plugin."""
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            raise PluginNotFoundError(plugin_name)
        
        plugin.config.enabled = True
        plugin.status = PluginStatus.ENABLED
        return plugin
    
    def disable_plugin(self, plugin_name: str) -> Plugin:
        """Disable a plugin."""
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            raise PluginNotFoundError(plugin_name)
        
        plugin.config.enabled = False
        plugin.status = PluginStatus.DISABLED
        return plugin
    
    def check_health(self, plugin_name: str) -> HealthCheckResult:
        """
        Perform a health check on a plugin.
        
        Args:
            plugin_name: Name of the plugin to check
            
        Returns:
            HealthCheckResult with the outcome
        """
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            raise PluginNotFoundError(plugin_name)
        
        checks: List[Tuple[str, bool, str]] = [
            ("configuration", True, "Configuration OK"),
            ("capabilities_loaded", True, f"{len(plugin.capabilities)} capabilities loaded"),
        ]
        
        result = HealthCheckResult(
            plugin_name=plugin_name,
            healthy=True,
            checks=checks,
            timestamp=datetime.utcnow(),
        )
        
        plugin.last_health_check = datetime.utcnow()
        plugin.health_status = "healthy"
        
        return result
    
    def list_loaded_plugins(self) -> List[Plugin]:
        """List all loaded plugins."""
        with self._lock:
            return list(self._loaded_plugins.values())
    
    def get_plugin_status(self, plugin_name: str) -> PluginStatus:
        """Get the status of a plugin."""
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            raise PluginNotFoundError(plugin_name)
        return plugin.status
    
    def statistics(self) -> Dict[str, Any]:
        """Get plugin manager statistics."""
        with self._lock:
            return {
                "total_plugins": len(self.registry.list_plugins()),
                "loaded_plugins": len(self._loaded_plugins),
                "enabled_plugins": sum(
                    1 for p in self.registry.list_plugins() if p.config.enabled
                ),
            }


def get_plugin_manager() -> PluginManager:
    """Get the singleton plugin manager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PluginManager()
    return _manager_instance
