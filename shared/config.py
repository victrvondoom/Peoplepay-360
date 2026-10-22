"""Centralized configuration management for PeoplePay 360.

This module provides a unified configuration system that can read from
environment variables, configuration files, and service discovery.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Generic, TypeVar

import yaml


T = TypeVar('T')


# =============================================================================
# CONFIGURATION SOURCES
# =============================================================================

class ConfigSource(str, Enum):
    """Configuration source priority."""
    ENVIRONMENT = "environment"  # Highest priority
    COMMAND_LINE = "command_line"
    CONFIG_FILE = "config_file"
    DEFAULT = "default"  # Lowest priority


@dataclass
class ConfigValue:
    """A configuration value with its source and metadata."""
    value: Any
    source: ConfigSource
    raw_value: str | None = None
    description: str | None = None
    is_secret: bool = False
    
    def __str__(self) -> str:
        if self.is_secret:
            return "***"  # Mask secret values
        return str(self.value)
    
    def __repr__(self) -> str:
        return f"ConfigValue(value={self.value!r}, source={self.source.value})"


# =============================================================================
# BASE CONFIGURATION
# =============================================================================

@dataclass
class BaseConfig:
    """Base configuration with common settings."""
    # Service identity
    service_name: str = "peoplepay"
    service_version: str = "360.0.0"
    environment: str = "development"
    
    # Hosting
    host: str = "127.0.0.1"
    port: int = 8080
    bind_address: str = "127.0.0.1:8080"
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str | None = None
    
    # Security
    secret_key: str | None = None
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    
    # Rate limiting
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    
    # Database
    database_url: str | None = None
    
    # Redis/FalkorDB
    redis_url: str | None = None
    falkordb_url: str | None = None
    falkordb_port: int = 16380
    falkordb_graph_name: str = "peoplepay_echo"
    
    # Debug
    debug: bool = False
    
    @classmethod
    def from_env(cls) -> "BaseConfig":
        """Load configuration from environment variables."""
        return cls(
            service_name=os.getenv("PEOPLEPAY_SERVICE_NAME", "peoplepay"),
            service_version=os.getenv("PEOPLEPAY_SERVICE_VERSION", "360.0.0"),
            environment=os.getenv("PEOPLEPAY_ENVIRONMENT", os.getenv("ENVIRONMENT", "development")),
            host=os.getenv("PEOPLEPAY_HOST", os.getenv("HOST", "127.0.0.1")),
            port=int(os.getenv("PEOPLEPAY_PORT", os.getenv("PORT", "8080"))),
            bind_address=os.getenv("PEOPLEPAY_BIND_ADDRESS", "127.0.0.1:8080"),
            log_level=os.getenv("PEOPLEPAY_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")),
            log_format=os.getenv("PEOPLEPAY_LOG_FORMAT", os.getenv("LOG_FORMAT", "json")),
            log_file=os.getenv("PEOPLEPAY_LOG_FILE"),
            secret_key=os.getenv("PEOPLEPAY_SECRET_KEY"),
            jwt_secret=os.getenv("PEOPLEPAY_JWT_SECRET"),
            jwt_algorithm=os.getenv("PEOPLEPAY_JWT_ALGORITHM", "HS256"),
            jwt_expiry_hours=int(os.getenv("PEOPLEPAY_JWT_EXPIRY_HOURS", "24")),
            rate_limit_requests=int(os.getenv("PEOPLEPAY_RATE_LIMIT_REQUESTS", "60")),
            rate_limit_window_seconds=int(os.getenv("PEOPLEPAY_RATE_LIMIT_WINDOW_SECONDS", "60")),
            database_url=os.getenv("PEOPLEPAY_DATABASE_URL"),
            redis_url=os.getenv("PEOPLEPAY_REDIS_URL"),
            falkordb_url=os.getenv("PEOPLEPAY_FALKORDB_URL"),
            falkordb_port=int(os.getenv("PEOPLEPAY_FALKORDB_PORT", "16380")),
            falkordb_graph_name=os.getenv("PEOPLEPAY_FALKORDB_GRAPH_NAME", "peoplepay_echo"),
            debug=os.getenv("PEOPLEPAY_DEBUG", "").lower() in ("true", "1", "yes"),
        )


# =============================================================================
# SERVICE CONFIGURATION
# =============================================================================

@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str | None = None
    pool_size: int = 10
    pool_timeout: int = 30
    echo: bool = True  # Log SQL queries
    
    @classmethod
    def from_env(cls, prefix: str = "PEOPLEPAY_DATABASE") -> "DatabaseConfig":
        return cls(
            url=os.getenv(f"{prefix}_URL"),
            pool_size=int(os.getenv(f"{prefix}_POOL_SIZE", "10")),
            pool_timeout=int(os.getenv(f"{prefix}_POOL_TIMEOUT", "30")),
            echo=os.getenv(f"{prefix}_ECHO", "").lower() in ("true", "1", "yes"),
        )


@dataclass
class CacheConfig:
    """Cache configuration."""
    url: str | None = None
    type: str = "redis"  # redis, memory
    ttl_seconds: int = 3600
    prefix: str = "peoplepay"
    
    @classmethod
    def from_env(cls) -> "CacheConfig":
        return cls(
            url=os.getenv("PEOPLEPAY_CACHE_URL"),
            type=os.getenv("PEOPLEPAY_CACHE_TYPE", "redis"),
            ttl_seconds=int(os.getenv("PEOPLEPAY_CACHE_TTL_SECONDS", "3600")),
            prefix=os.getenv("PEOPLEPAY_CACHE_PREFIX", "peoplepay"),
        )


@dataclass
class AuthConfig:
    """Authentication configuration."""
    # JWT settings
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    jwt_refresh_hours: int = 168  # 7 days
    
    # Session
    session_timeout_hours: int = 24
    session_rolling: bool = True
    
    # OAuth/Social login
    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    
    # Multi-factor
    mfa_required: bool = False
    mfa_issuer: str = "PeoplePay"
    
    # Password policies
    min_password_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True
    
    @classmethod
    def from_env(cls) -> "AuthConfig":
        return cls(
            jwt_secret=os.getenv("PEOPLEPAY_JWT_SECRET"),
            jwt_algorithm=os.getenv("PEOPLEPAY_JWT_ALGORITHM", "HS256"),
            jwt_expiry_hours=int(os.getenv("PEOPLEPAY_JWT_EXPIRY_HOURS", "24")),
            jwt_refresh_hours=int(os.getenv("PEOPLEPAY_JWT_REFRESH_HOURS", "168")),
            session_timeout_hours=int(os.getenv("PEOPLEPAY_SESSION_TIMEOUT_HOURS", "24")),
            session_rolling=os.getenv("PEOPLEPAY_SESSION_ROLLING", "").lower() in ("true", "1", "yes"),
            google_client_id=os.getenv("PEOPLEPAY_GOOGLE_CLIENT_ID"),
            google_client_secret=os.getenv("PEOPLEPAY_GOOGLE_CLIENT_SECRET"),
            github_client_id=os.getenv("PEOPLEPAY_GITHUB_CLIENT_ID"),
            github_client_secret=os.getenv("PEOPLEPAY_GITHUB_CLIENT_SECRET"),
            mfa_required=os.getenv("PEOPLEPAY_MFA_REQUIRED", "").lower() in ("true", "1", "yes"),
            mfa_issuer=os.getenv("PEOPLEPAY_MFA_ISSUER", "PeoplePay"),
            min_password_length=int(os.getenv("PEOPLEPAY_MIN_PASSWORD_LENGTH", "8")),
            require_uppercase=os.getenv("PEOPLEPAY_REQUIRE_UPPERCASE", "").lower() in ("true", "1", "yes"),
            require_lowercase=os.getenv("PEOPLEPAY_REQUIRE_LOWERCASE", "").lower() in ("true", "1", "yes"),
            require_digit=os.getenv("PEOPLEPAY_REQUIRE_DIGIT", "").lower() in ("true", "1", "yes"),
            require_special=os.getenv("PEOPLEPAY_REQUIRE_SPECIAL", "").lower() in ("true", "1", "yes"),
        )


@dataclass
class ServiceConfig:
    """Service-specific configuration.
    
    This is the main configuration class that aggregates all service settings.
    """
    base: BaseConfig = field(default_factory=BaseConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    
    # Payment settings
    payment_sandbox_enabled: bool = True
    payment_require_approval: bool = True
    payment_max_amount: int | None = None  # In minor units
    
    # Model Gateway settings
    model_gateway_url: str | None = None
    model_gateway_timeout: int = 60
    
    # ECHO settings
    echo_url: str | None = None
    echo_graph_name: str = "peoplepay_echo"
    echo_admin_token: str | None = None
    
    # Journey settings
    journey_database_path: str = "peoplepay-journey.sqlite3"
    
    # Gateway settings
    gateway_secret: str | None = None
    gateway_rate_limit: int = 60
    gateway_rate_window: int = 60
    gateway_max_body_bytes: int = 1048576
    
    # Feature flags
    features: dict[str, bool] = field(default_factory=lambda: {
        "assistance": False,
        "hypergrid": False,
        "native_providers": False,
    })
    
    @classmethod
    def from_env(cls) -> "ServiceConfig":
        """Load configuration from environment variables."""
        features = {}
        # Load feature flags from environment
        feature_prefixes = ["PEOPLEPAY_FEATURE_", "BEACON_GATEWAY_"]
        for key, value in os.environ.items():
            for prefix in feature_prefixes:
                if key.startswith(prefix):
                    feature_name = key[len(prefix):].lower().replace("_", "-")
                    features[feature_name] = value.lower() in ("true", "1", "yes")
        
        return cls(
            base=BaseConfig.from_env(),
            database=DatabaseConfig.from_env(),
            cache=CacheConfig.from_env(),
            auth=AuthConfig.from_env(),
            payment_sandbox_enabled=os.getenv("PEOPLEPAY_PAYMENT_SANDBOX", "").lower() in ("true", "1", "yes"),
            payment_require_approval=os.getenv("PEOPLEPAY_PAYMENT_REQUIRE_APPROVAL", "").lower() in ("true", "1", "yes"),
            payment_max_amount=int(os.getenv("PEOPLEPAY_PAYMENT_MAX_AMOUNT")) if os.getenv("PEOPLEPAY_PAYMENT_MAX_AMOUNT") else None,
            model_gateway_url=os.getenv("PEOPLEPAY_MODEL_GATEWAY_URL"),
            model_gateway_timeout=int(os.getenv("PEOPLEPAY_MODEL_GATEWAY_TIMEOUT", "60")),
            echo_url=os.getenv("PEOPLEPAY_ECHO_URL"),
            echo_graph_name=os.getenv("PEOPLEPAY_ECHO_GRAPH_NAME", "peoplepay_echo"),
            echo_admin_token=os.getenv("PEOPLEPAY_ECHO_ADMIN_TOKEN"),
            journey_database_path=os.getenv("PEOPLEPAY_JOURNEY_DB", "peoplepay-journey.sqlite3"),
            gateway_secret=os.getenv("BEACON_GATEWAY_SECRET"),
            gateway_rate_limit=int(os.getenv("BEACON_GATEWAY_RATE_LIMIT", "60")),
            gateway_rate_window=int(os.getenv("BEACON_GATEWAY_RATE_WINDOW_SECONDS", "60")),
            gateway_max_body_bytes=int(os.getenv("BEACON_GATEWAY_MAX_BODY_BYTES", "1048576")),
            features=features,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "base": self.base.__dict__,
            "database": self.database.__dict__,
            "cache": self.cache.__dict__,
            "auth": {k: v for k, v in self.auth.__dict__.items() if not k.startswith('_')},
            "payment_sandbox_enabled": self.payment_sandbox_enabled,
            "payment_require_approval": self.payment_require_approval,
            "payment_max_amount": self.payment_max_amount,
            "model_gateway_url": self.model_gateway_url,
            "model_gateway_timeout": self.model_gateway_timeout,
            "echo_url": self.echo_url,
            "echo_graph_name": self.echo_graph_name,
            "journey_database_path": self.journey_database_path,
            "gateway_secret": "***" if self.gateway_secret else None,
            "features": self.features,
        }


# =============================================================================
# CONFIGURATION MANAGER
# =============================================================================

class Config:
    """Centralized configuration manager.
    
    This is a singleton that provides access to configuration across the application.
    It supports loading from multiple sources with proper precedence.
    """
    
    _instance: "Config | None" = None
    _config: ServiceConfig | None = None
    
    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: ServiceConfig | None = None) -> None:
        if Config._config is None:
            Config._config = config or ServiceConfig.from_env()
    
    @classmethod
    def get_instance(cls) -> "Config":
        """Get the singleton instance."""
        if cls._instance is None:
            cls()
        return cls._instance
    
    @property
    def service(self) -> ServiceConfig:
        """Get the service configuration."""
        if Config._config is None:
            Config._config = ServiceConfig.from_env()
        return Config._config
    
    def reload(self) -> None:
        """Reload configuration from environment."""
        Config._config = ServiceConfig.from_env()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dotted key path."""
        parts = key.split('.')
        value = Config._config
        
        for part in parts:
            if value is None:
                return default
            if isinstance(value, dict):
                value = value.get(part, default)
            else:
                value = getattr(value, part, default)
        
        return value if value is not None else default


# Module-level accessor
def get_config() -> Config:
    """Get the configuration singleton."""
    return Config.get_instance()


# =============================================================================
# CONFIGURATION LOADERS
# =============================================================================

class ConfigLoader:
    """Load configuration from various sources."""
    
    @staticmethod
    def from_yaml(path: str | Path) -> dict[str, Any]:
        """Load configuration from YAML file."""
        path = Path(path)
        if not path.exists():
            return {}
        with open(path) as f:
            return yaml.safe_load(f)
    
    @staticmethod
    def from_json(path: str | Path) -> dict[str, Any]:
        """Load configuration from JSON file."""
        path = Path(path)
        if not path.exists():
            return {}
        with open(path) as f:
            return json.load(f)
    
    @staticmethod
    def from_py(path: str | Path) -> dict[str, Any]:
        """Load configuration from Python file."""
        path = Path(path)
        if not path.exists():
            return {}
        # Read and execute the Python file to get a config dict
        import importlib.util
        spec = importlib.util.spec_from_file_location("config_module", path)
        if spec is None or spec.loader is None:
            return {}
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            if hasattr(module, 'CONFIG'):
                return module.CONFIG
            elif hasattr(module, 'config'):
                return module.config
            else:
                return {}
        except Exception:
            return {}
    
    @staticmethod
    def from_env(prefix: str = "PEOPLEPAY_", lowercase_keys: bool = True) -> dict[str, Any]:
        """Load configuration from environment variables with prefix."""
        result = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):]
                if lowercase_keys:
                    config_key = config_key.lower()
                # Try to parse as JSON
                if value.lower() in ("true", "false"):
                    result[config_key] = value.lower() == "true"
                elif value.isdigit():
                    result[config_key] = int(value)
                elif re.match(r'^\d+\.\d+$', value):
                    result[config_key] = float(value)
                else:
                    result[config_key] = value
        return result


# =============================================================================
# SERVICE DISCOVERY
# =============================================================================

@dataclass
class ServiceInfo:
    """Information about a registered service."""
    name: str
    description: str
    url: str | None = None
    version: str = "1.0.0"
    status: str = "unknown"  # healthy, degraded, unhealthy, unavailable
    capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


class ServiceRegistry:
    """Registry of available services for discovery."""
    
    def __init__(self) -> None:
        self._services: dict[str, ServiceInfo] = {}
    
    def register(self, info: ServiceInfo) -> None:
        """Register a service."""
        self._services[info.name] = info
    
    def get(self, name: str) -> ServiceInfo | None:
        """Get a service by name."""
        return self._services.get(name)
    
    def list(self) -> list[ServiceInfo]:
        """List all registered services."""
        return list(self._services.values())
    
    def healthy(self) -> list[ServiceInfo]:
        """List all healthy services."""
        return [s for s in self._services.values() if s.status == "healthy"]
    
    @classmethod
    def from_environment(cls) -> "ServiceRegistry":
        """Create registry from environment variables."""
        registry = cls()
        
        # Register known services from environment
        service_mappings = {
            "PEOPLEPAY_ECHO_URL": ServiceInfo(
                name="echo",
                description="PeoplePay ECHO evidence service",
                url=os.getenv("PEOPLEPAY_ECHO_URL"),
                version="0.1.0",
                capabilities=["evidence", "decision", "provenance"],
            ),
            "PEOPLEPAY_GREENCHAIN_URL": ServiceInfo(
                name="greenchain",
                description="GreenChain supplier intelligence",
                url=os.getenv("PEOPLEPAY_GREENCHAIN_URL"),
                version="1.0.0",
                capabilities=["supplier_discovery", "sustainability"],
            ),
            "PEOPLEPAY_INFLATIONFORGE_URL": ServiceInfo(
                name="inflationforge",
                description="InflationForge price intelligence",
                url=os.getenv("PEOPLEPAY_INFLATIONFORGE_URL"),
                version="1.0.0",
                capabilities=["price_intelligence", "market_data"],
            ),
            "PEOPLEPAY_PROXY_URL": ServiceInfo(
                name="proxy",
                description="PROXY dispute resolution",
                url=os.getenv("PEOPLEPAY_PROXY_URL"),
                version="1.0.0",
                capabilities=["dispute_management", "after_sales"],
            ),
            "PEOPLEPAY_RUMI_URL": ServiceInfo(
                name="rumi",
                description="Rumi room planning",
                url=os.getenv("PEOPLEPAY_RUMI_URL"),
                version="1.0.0",
                capabilities=["room_planning", "furniture_discovery"],
            ),
            "PEOPLEPAY_BEACON_URL": ServiceInfo(
                name="beacon",
                description="Beacon platform monitoring",
                url=os.getenv("PEOPLEPAY_BEACON_URL"),
                version="1.0.0",
                capabilities=["monitoring", "incident_response"],
            ),
        }
        
        for env_var, info in service_mappings.items():
            if info.url:
                registry.register(info)
        
        return registry
