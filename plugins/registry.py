"""
Plugin Registry

Manages the registration and discovery of plugins and their capabilities.
"""

import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from plugins.models import (
    Plugin,
    PluginCapability,
    PluginConfig,
    PluginManifest,
    PluginStatus,
    CapabilityContract,
    CapabilityType,
)
from plugins.errors import (
    PluginError,
    PluginNotFoundError,
    CapabilityNotFoundError,
    InvalidPluginError,
)


# Singleton instance
_registry_instance: Optional["PluginRegistry"] = None


class PluginRegistry:
    """
    Registry for managing plugins and their capabilities.
    
    Provides:
    - Plugin registration and unregistration
    - Capability discovery
    - Plugin lookup by name or capability
    - Versioned contract management
    - Capability categorization
    """
    
    def __init__(self):
        """Initialize the plugin registry."""
        self._plugins: Dict[str, Plugin] = {}
        self._capabilities_by_name: Dict[str, PluginCapability] = {}
        self._capabilities_by_type: Dict[CapabilityType, List[PluginCapability]] = {}
        self._capabilities_by_category: Dict[str, List[PluginCapability]] = {}
        self._capabilities_by_tag: Dict[str, List[PluginCapability]] = {}
        self._lock = threading.Lock()
    
    def register_plugin(
        self,
        manifest: PluginManifest,
        config: Optional[PluginConfig] = None,
    ) -> Plugin:
        """
        Register a plugin.
        
        Args:
            manifest: Plugin manifest
            config: Optional configuration
            
        Returns:
            The registered Plugin object
        """
        with self._lock:
            if manifest.name in self._plugins:
                # Update existing plugin
                plugin = self._plugins[manifest.name]
                plugin.manifest = manifest
                if config:
                    plugin.config = config
                plugin.updated_at = datetime.utcnow()
            else:
                # Create new plugin
                plugin = Plugin(
                    manifest=manifest,
                    config=config or PluginConfig(
                        plugin_name=manifest.name,
                        enabled=True,
                    ),
                    status=PluginStatus.DISABLED,
                )
                self._plugins[manifest.name] = plugin
            
            # Register capabilities
            self._register_capabilities(plugin)
            
            return plugin
    
    def _register_capabilities(self, plugin: Plugin):
        """Register all capabilities of a plugin."""
        for capability_contract in plugin.manifest.capabilities:
            # Create full capability name
            full_name = f"{plugin.manifest.name}.{capability_contract.name}"
            
            capability = PluginCapability(
                plugin_name=plugin.manifest.name,
                contract=capability_contract,
                is_available=plugin.status in (PluginStatus.ENABLED, PluginStatus.LOADED, PluginStatus.READY),
                is_enabled=plugin.config.enabled,
            )
            
            # Register by name
            self._capabilities_by_name[full_name] = capability
            
            # Register by type
            self._capabilities_by_type.setdefault(capability_contract.capability_type, []).append(capability)
            
            # Register by category
            self._capabilities_by_category.setdefault(capability_contract.category, []).append(capability)
            
            # Register by tags
            for tag in capability_contract.tags:
                self._capabilities_by_tag.setdefault(tag, []).append(capability)
            
            # Add to plugin
            plugin.capabilities[capability_contract.name] = capability
    
    def unregister_plugin(self, plugin_name: str) -> bool:
        """
        Unregister a plugin.
        
        Args:
            plugin_name: Name of the plugin to unregister
            
        Returns:
            True if unregistered, False if not found
        """
        with self._lock:
            if plugin_name not in self._plugins:
                return False
            
            plugin = self._plugins[plugin_name]
            
            # Remove all capabilities
            for cap_name, capability in plugin.capabilities.items():
                full_name = f"{plugin_name}.{cap_name}"
                self._capabilities_by_name.pop(full_name, None)
                
                # Remove from type index
                if capability.contract.capability_type in self._capabilities_by_type:
                    self._capabilities_by_type[capability.contract.capability_type].remove(capability)
                
                # Remove from category index
                if capability.contract.category in self._capabilities_by_category:
                    self._capabilities_by_category[capability.contract.category].remove(capability)
                
                # Remove from tag indices
                for tag in capability.contract.tags:
                    if tag in self._capabilities_by_tag:
                        self._capabilities_by_tag[tag].remove(capability)
            
            del self._plugins[plugin_name]
            return True
    
    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        with self._lock:
            return self._plugins.get(plugin_name)
    
    def list_plugins(
        self,
        status: Optional[PluginStatus] = None,
        limit: int = 100,
    ) -> List[Plugin]:
        """List all plugins with optional filtering."""
        with self._lock:
            plugins = list(self._plugins.values())
            if status:
                plugins = [p for p in plugins if p.status == status]
            return plugins[:limit]
    
    def get_capability(
        self,
        capability_name: str,
    ) -> Optional[PluginCapability]:
        """
        Get a capability by its full name (plugin.capability).
        
        Args:
            capability_name: Full capability name
            
        Returns:
            PluginCapability or None
        """
        with self._lock:
            return self._capabilities_by_name.get(capability_name)
    
    def list_capabilities(
        self,
        capability_type: Optional[CapabilityType] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        plugin_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[PluginCapability]:
        """List capabilities with optional filtering."""
        with self._lock:
            if capability_type:
                return self._capabilities_by_type.get(capability_type, [])[:limit]
            elif category:
                return self._capabilities_by_category.get(category, [])[:limit]
            elif tag:
                return self._capabilities_by_tag.get(tag, [])[:limit]
            elif plugin_name:
                plugin = self._plugins.get(plugin_name)
                if plugin:
                    return list(plugin.capabilities.values())[:limit]
                return []
            else:
                return list(self._capabilities_by_name.values())[:limit]
    
    def find_capabilities(
        self,
        query: str,
        limit: int = 10,
    ) -> List[PluginCapability]:
        """
        Find capabilities matching a query string.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching capabilities
        """
        with self._lock:
            results = []
            query_lower = query.lower()
            
            for capability in self._capabilities_by_name.values():
                if (query_lower in capability.contract.name.lower() or
                    query_lower in capability.contract.description.lower()):
                    results.append(capability)
                    if len(results) >= limit:
                        break
            
            return results
    
    def get_capabilities_for_plugin(self, plugin_name: str) -> List[PluginCapability]:
        """Get all capabilities for a specific plugin."""
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            raise PluginNotFoundError(plugin_name)
        return list(plugin.capabilities.values())
    
    def get_plugin_for_capability(self, capability_name: str) -> Optional[Plugin]:
        """Get the plugin that provides a capability."""
        capability = self.get_capability(capability_name)
        if not capability:
            return None
        return self.get_plugin(capability.plugin_name)
    
    def has_capability(self, capability_name: str) -> bool:
        """Check if a capability is available."""
        return self.get_capability(capability_name) is not None
    
    def get_contract(self, capability_name: str) -> Optional[CapabilityContract]:
        """Get the contract for a capability."""
        capability = self.get_capability(capability_name)
        if not capability:
            return None
        return capability.contract
    
    def validate_contract_compatibility(
        self,
        capability_name: str,
        version: str,
    ) -> bool:
        """
        Check if a capability contract version is compatible.
        
        Args:
            capability_name: Full capability name
            version: Version to check
            
        Returns:
            True if compatible
        """
        contract = self.get_contract(capability_name)
        if not contract:
            return False
        
        # Simple version comparison (major.minor)
        try:
            contract_parts = contract.version.split(".")
            version_parts = version.split(".")
            
            for i in range(min(len(contract_parts), len(version_parts))):
                contract_num = int(contract_parts[i])
                version_num = int(version_parts[i])
                if version_num < contract_num:
                    return False
                elif version_num > contract_num:
                    return True
            
            return True
        except (ValueError, IndexError):
            return False
    
    def statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        with self._lock:
            return {
                "plugin_count": len(self._plugins),
                "capability_count": len(self._capabilities_by_name),
                "by_type": {
                    ct.value: len(caps)
                    for ct, caps in self._capabilities_by_type.items()
                },
                "by_category": {
                    cat: len(caps)
                    for cat, caps in self._capabilities_by_category.items()
                },
                "by_tag": {
                    tag: len(caps)
                    for tag, caps in self._capabilities_by_tag.items()
                },
            }
    
    def clear(self) -> None:
        """Clear all registered plugins."""
        with self._lock:
            self._plugins.clear()
            self._capabilities_by_name.clear()
            self._capabilities_by_type.clear()
            self._capabilities_by_category.clear()
            self._capabilities_by_tag.clear()


def get_plugin_registry() -> PluginRegistry:
    """Get the singleton plugin registry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = PluginRegistry()
    return _registry_instance
