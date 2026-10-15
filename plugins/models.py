"""
Plugin and Integration Models
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
from uuid import uuid4


class PluginStatus(Enum):
    """Status of a plugin."""
    DISABLED = "disabled"
    ENABLED = "enabled"
    LOADED = "loaded"
    READY = "ready"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class CapabilityType(Enum):
    """Type of plugin capability."""
    SERVICE = "service"  # Provides a service
    TOOL = "tool"  # Provides a tool/function
    DATA_SOURCE = "data_source"  # Provides data
    PROCESSOR = "processor"  # Processes data
    VALIDATOR = "validator"  # Validates data
    TRANSFORMER = "transformer"  # Transforms data
    AGENT = "agent"  # Agent capability
    WORKFLOW = "workflow"  # Workflow capability


class ExecutionMode(Enum):
    """Execution mode for plugin capabilities."""
    SYNC = "sync"  # Synchronous execution
    ASYNC = "async"  # Asynchronous execution
    BATCH = "batch"  # Batch execution
    STREAMING = "streaming"  # Streaming execution


class PermissionLevel(Enum):
    """Permission levels for plugin capabilities."""
    READ = "read"  # Read-only operations
    WRITE = "write"  # Can modify data
    ADMIN = "admin"  # Administrative operations
    SYSTEM = "system"  # System-level operations


@dataclass
class CapabilityContract:
    """Defines the contract for a plugin capability."""
    name: str
    version: str = "1.0"
    description: str = ""
    capability_type: CapabilityType = CapabilityType.TOOL
    execution_mode: ExecutionMode = ExecutionMode.SYNC
    
    # Input/output schema
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    
    # Requirements
    required_permissions: List[PermissionLevel] = field(default_factory=list)
    required_config: List[str] = field(default_factory=list)
    
    # Limits
    max_retries: int = 3
    timeout_seconds: int = 60
    max_execution_time_seconds: int = 300
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    category: str = "general"
    is_idempotent: bool = False
    is_safe: bool = True


@dataclass
class PluginDependency:
    """Defines a dependency for a plugin."""
    name: str
    version: str = "*"
    optional: bool = False
    minimum_version: Optional[str] = None
    maximum_version: Optional[str] = None


@dataclass
class PluginManifest:
    """Plugin manifest defining its metadata and requirements."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    homepage: Optional[str] = None
    license: str = "MIT"
    
    # Capabilities provided by this plugin
    capabilities: List[CapabilityContract] = field(default_factory=list)
    
    # Dependencies
    dependencies: List[PluginDependency] = field(default_factory=list)
    
    # Configuration
    config_schema: Optional[Dict[str, Any]] = None
    default_config: Dict[str, Any] = field(default_factory=dict)
    
    # Runtime
    requires: List[str] = field(default_factory=list)  # Required Python packages
    python_version: str = ">=3.8"
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    category: str = "general"


@dataclass
class PluginConfig:
    """Configuration for a plugin instance."""
    plugin_name: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 0
    
    # Runtime settings
    max_retries: Optional[int] = None
    timeout_override: Optional[int] = None
    
    # Security
    allowed_permissions: List[PermissionLevel] = field(default_factory=list)
    restricted: bool = False


@dataclass
class PluginCapability:
    """A capability provided by a plugin."""
    plugin_name: str
    contract: CapabilityContract
    implementation: Optional[Callable[..., Any]] = None
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Status
    is_available: bool = True
    is_enabled: bool = True
    last_checked: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class Plugin:
    """Represents a loaded plugin."""
    manifest: PluginManifest
    config: PluginConfig
    status: PluginStatus = PluginStatus.DISABLED
    
    # Runtime
    loaded_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    health_status: Optional[str] = None
    error: Optional[str] = None
    
    # Capabilities
    capabilities: Dict[str, PluginCapability] = field(default_factory=dict)
    
    # Metadata
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FeatureFlag:
    """A feature flag that can enable/disable functionality."""
    name: str
    description: str = ""
    enabled: bool = False
    rollout_percentage: float = 0.0  # 0-100
    
    # Conditions
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    # Tags
    tags: List[str] = field(default_factory=list)
    environment: str = "production"


@dataclass
class ExecutionContext:
    """Context for plugin capability execution."""
    plugin_name: str
    capability_name: str
    
    # Input
    args: Tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)
    
    # Execution settings
    timeout: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Security
    caller_id: Optional[str] = None
    caller_permissions: List[PermissionLevel] = field(default_factory=list)
    organization_id: Optional[str] = None
    
    # Metadata
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExecutionResult:
    """Result of a plugin capability execution."""
    context: ExecutionContext
    success: bool = True
    result: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    
    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    
    # Retry information
    retry_count: int = 0
    last_error: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """Result of a plugin health check."""
    plugin_name: str
    healthy: bool = True
    checks: List[Tuple[str, bool, str]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None
