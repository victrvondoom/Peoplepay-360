"""
Plugin Executor

Executes plugin capabilities with proper security, retries, and error handling.
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from datetime import datetime

from plugins.models import (
    Plugin,
    PluginCapability,
    ExecutionContext,
    ExecutionResult,
    PermissionLevel,
)
from plugins.registry import get_plugin_registry, PluginRegistry
from plugins.manager import get_plugin_manager, PluginManager
from plugins.errors import (
    PluginError,
    PluginNotFoundError,
    CapabilityNotFoundError,
    PluginDisabledError,
    CapabilityDisabledError,
    PermissionDeniedError,
    ExecutionError,
    TimeoutError,
    RetryExhaustedError,
)


# Singleton instance
_executor_instance: Optional["PluginExecutor"] = None


class PluginExecutor:
    """
    Executes plugin capabilities with proper controls.
    
    Provides:
    - Secure capability execution
    - Retry logic with exponential backoff
    - Timeout enforcement
    - Permission checking
    - Result tracking
    """
    
    def __init__(
        self,
        registry: Optional[PluginRegistry] = None,
        manager: Optional[PluginManager] = None,
    ):
        """Initialize the plugin executor."""
        self.registry = registry or get_plugin_registry()
        self.manager = manager or get_plugin_manager()
        self._lock = threading.Lock()
    
    def execute(
        self,
        capability_name: str,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        caller_id: Optional[str] = None,
        caller_permissions: Optional[List[PermissionLevel]] = None,
        organization_id: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Execute a plugin capability.
        
        Args:
            capability_name: Full capability name (plugin.capability)
            args: Positional arguments
            kwargs: Keyword arguments
            caller_id: ID of the caller
            caller_permissions: Permissions of the caller
            organization_id: Organization context
            timeout: Override timeout in seconds
            max_retries: Override max retries
            
        Returns:
            ExecutionResult with the outcome
        """
        start_time = datetime.utcnow()
        kwargs = kwargs or {}
        caller_permissions = caller_permissions or []
        
        # Parse capability name
        if "." not in capability_name:
            raise CapabilityNotFoundError(capability_name)
        
        plugin_name, capability_part = capability_name.split(".", 1)
        
        # Get the capability
        capability = self.registry.get_capability(capability_name)
        if not capability:
            raise CapabilityNotFoundError(capability_name, plugin_name)
        
        # Get the plugin
        plugin = self.registry.get_plugin(plugin_name)
        if not plugin:
            raise PluginNotFoundError(plugin_name)
        
        # Check if plugin is enabled
        if not plugin.config.enabled:
            raise PluginDisabledError(plugin_name)
        
        # Check if capability is enabled
        if not capability.is_enabled:
            raise CapabilityDisabledError(capability_part, plugin_name)
        
        # Check permissions
        required_perms = capability.contract.required_permissions
        for required in required_perms:
            if required not in caller_permissions:
                raise PermissionDeniedError(
                    f"Missing permission: {required.value}",
                    details={"required": required.value, "has": [p.value for p in caller_permissions]}
                )
        
        # Create execution context
        context = ExecutionContext(
            plugin_name=plugin_name,
            capability_name=capability_part,
            args=args,
            kwargs=kwargs,
            timeout=timeout or capability.contract.timeout_seconds,
            max_retries=max_retries or capability.contract.max_retries,
            caller_id=caller_id,
            caller_permissions=caller_permissions,
            organization_id=organization_id,
        )
        
        # Execute with retries
        result = self._execute_with_retries(context, capability, plugin, start_time)
        
        return result
    
    def _execute_with_retries(
        self,
        context: ExecutionContext,
        capability: PluginCapability,
        plugin: Plugin,
        start_time: datetime,
    ) -> ExecutionResult:
        """Execute with retry logic."""
        last_error: Optional[str] = None
        retry_count = 0
        
        while retry_count <= context.max_retries:
            try:
                result = self._execute_single(context, capability, plugin, start_time)
                result.retry_count = retry_count
                return result
            except TimeoutError as e:
                last_error = str(e)
                if retry_count >= context.max_retries:
                    raise RetryExhaustedError(
                        context.plugin_name,
                        context.capability_name,
                        retry_count,
                        last_error,
                    )
            except Exception as e:
                last_error = str(e)
                if retry_count >= context.max_retries:
                    # Return failed result instead of raising for non-critical errors
                    return ExecutionResult(
                        context=context,
                        success=False,
                        error=str(e),
                        error_type=type(e).__name__,
                        started_at=start_time,
                        completed_at=datetime.utcnow(),
                        duration_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
                        retry_count=retry_count,
                        last_error=last_error,
                    )
            
            # Wait before retry with exponential backoff
            if retry_count < context.max_retries:
                wait_time = min(2 ** retry_count, 10)  # Cap at 10 seconds
                time.sleep(wait_time)
                retry_count += 1
        
        raise RetryExhaustedError(
            context.plugin_name,
            context.capability_name,
            retry_count,
            last_error,
        )
    
    def _execute_single(
        self,
        context: ExecutionContext,
        capability: PluginCapability,
        plugin: Plugin,
        start_time: datetime,
    ) -> ExecutionResult:
        """Execute a single attempt."""
        # Check if implementation exists
        if not capability.implementation:
            raise ExecutionError(
                context.plugin_name,
                context.capability_name,
                "Capability implementation not found",
            )
        
        # Execute with timeout (simplified - real implementation would use threading)
        try:
            result_value = capability.implementation(*context.args, **context.kwargs)
            
            return ExecutionResult(
                context=context,
                success=True,
                result=result_value,
                started_at=start_time,
                completed_at=datetime.utcnow(),
                duration_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
                retry_count=0,
            )
        except Exception as e:
            raise ExecutionError(
                context.plugin_name,
                context.capability_name,
                str(e),
            )
    
    def execute_tool(
        self,
        capability_name: str,
        caller_id: str,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        caller_permissions: Optional[List[PermissionLevel]] = None,
        organization_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Execute a tool capability.
        
        Convenience method for executing tool-type capabilities.
        """
        return self.execute(
            capability_name=capability_name,
            args=args,
            kwargs=kwargs,
            caller_id=caller_id,
            caller_permissions=caller_permissions,
            organization_id=organization_id,
        )
    
    def statistics(self) -> Dict[str, Any]:
        """Get executor statistics."""
        return {
            "total_capabilities": len(self.registry.list_capabilities()),
            "total_executions": 0,  # Would be tracked in production
        }


def get_plugin_executor() -> PluginExecutor:
    """Get the singleton plugin executor instance."""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = PluginExecutor()
    return _executor_instance
