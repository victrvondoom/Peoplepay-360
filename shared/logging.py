"""Structured logging for PeoplePay 360.

This module provides consistent structured logging across all services.
Logs are formatted as JSON by default for easy parsing and analysis.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog


# =============================================================================
# LOG CONTEXT
# =============================================================================

@dataclass
class LogContext:
    """Contextual information to include in log entries.
    
    This can be used to track request IDs, user IDs, and other contextual data.
    """
    request_id: str | None = None
    correlation_id: str | None = None
    user_id: str | None = None
    organization_id: str | None = None
    service: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None
    task_id: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}
    
    def with_request(self, request_id: str | None = None, correlation_id: str | None = None) -> "LogContext":
        """Create a new context with request tracking."""
        return LogContext(
            request_id=request_id or self.request_id,
            correlation_id=correlation_id or self.correlation_id,
            user_id=self.user_id,
            organization_id=self.organization_id,
            service=self.service,
            session_id=self.session_id,
            workflow_id=self.workflow_id,
            task_id=self.task_id,
        )
    
    def with_user(self, user_id: str | None = None, organization_id: str | None = None) -> "LogContext":
        """Create a new context with user tracking."""
        return LogContext(
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            user_id=user_id or self.user_id,
            organization_id=organization_id or self.organization_id,
            service=self.service,
            session_id=self.session_id,
            workflow_id=self.workflow_id,
            task_id=self.task_id,
        )
    
    def with_workflow(self, workflow_id: str | None = None, task_id: str | None = None) -> "LogContext":
        """Create a new context with workflow tracking."""
        return LogContext(
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            user_id=self.user_id,
            organization_id=self.organization_id,
            service=self.service,
            session_id=self.session_id,
            workflow_id=workflow_id or self.workflow_id,
            task_id=task_id or self.task_id,
        )


# Thread-local and async-local context storage
_context_var: ContextVar[LogContext | None] = ContextVar('log_context', default=None)
_thread_local = threading.local()


def get_context() -> LogContext:
    """Get the current log context."""
    # Try context var first (async)
    ctx = _context_var.get()
    if ctx:
        return ctx
    # Try thread local (sync)
    if hasattr(_thread_local, 'context'):
        return _thread_local.context
    return LogContext()


def set_context(context: LogContext | None = None) -> None:
    """Set the current log context."""
    if context is None:
        context = LogContext()
    _context_var.set(context)
    _thread_local.context = context


# =============================================================================
# LOG LEVELS AND FORMATTERS
# =============================================================================

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structlog."""
    
    def __init__(self, include_timestamp: bool = True, include_level: bool = True):
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_level = include_level
    
    def format(self, record: logging.LogRecord) -> str:
        # structlog already handles the formatting
        # This is just a pass-through for compatibility
        return super().format(record)


def add_timestamp(logger: structlog.BoundLogger, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add timestamp to log entries."""
    event_dict['timestamp'] = datetime.now(timezone.utc).isoformat()
    return event_dict


def add_context(logger: structlog.BoundLogger, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add context to log entries."""
    ctx = get_context()
    context_dict = ctx.to_dict()
    
    # Add context fields that don't already exist
    for key, value in context_dict.items():
        if key not in event_dict:
            event_dict[key] = value
    
    return event_dict


def add_service_info(logger: structlog.BoundLogger, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add service information to log entries."""
    from shared.config import get_config
    
    config = get_config()
    service_config = config.service
    
    event_dict['service'] = event_dict.get('service') or service_config.service_name
    event_dict['version'] = event_dict.get('version') or service_config.service_version
    event_dict['environment'] = event_dict.get('environment') or service_config.environment
    
    return event_dict


# =============================================================================
# LOGGER SETUP
# =============================================================================

def setup_logging(
    level: str | int | None = None,
    format: str = "json",
    log_file: str | None = None,
    service_name: str | None = None,
    include_timestamp: bool = True,
) -> structlog.BoundLogger:
    """Set up structured logging.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) or int
        format: Log format ('json' or 'text')
        log_file: Optional path to log file
        service_name: Service name to include in logs
        include_timestamp: Whether to include timestamp in logs
    
    Returns:
        Configured logger
    """
    # Determine log level
    if level is None:
        from shared.config import get_config
        config = get_config()
        level = config.service.base.log_level
    
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    
    # Create shared processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_timestamp,
        add_context,
        add_service_info,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    
    # Add stack info for debug logs
    if level <= logging.DEBUG:
        shared_processors.append(structlog.processors.StackInfoFormatter())
    
    # Configure based on format
    if format == "json":
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    
    # Configure standard library logging
    logging.basicConfig(
        level=level,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        format='%(message)s',  # structlog handles the formatting
    )
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Set up root logger
    root_logger = structlog.get_logger()
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONFormatter())
        logging.getLogger().addHandler(file_handler)
    
    # Set service name if provided
    if service_name:
        set_context(LogContext(service=service_name))
    
    return root_logger


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structured logger with the given name.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Bound logger with context
    """
    logger = structlog.get_logger(name or "peoplepay")
    return logger


# =============================================================================
# LOG HELPERS
# =============================================================================

def log_request(
    logger: structlog.BoundLogger,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    body: Any = None,
) -> structlog.BoundLogger:
    """Log an HTTP request."""
    extra = {
        "http_method": method,
        "http_path": path,
    }
    
    if params:
        # Filter out sensitive params
        filtered_params = {k: v for k, v in params.items() if k.lower() not in ('password', 'token', 'secret', 'key')}
        extra["http_query_params"] = filtered_params
    
    if headers:
        # Filter out sensitive headers
        filtered_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ('authorization', 'cookie', 'x-api-key', 'x-secret-key')
        }
        extra["http_headers"] = filtered_headers
    
    if body:
        # Don't log large bodies
        body_str = str(body)
        if len(body_str) > 1000:
            body_str = body_str[:1000] + "... [truncated]"
        extra["http_body"] = body_str
    
    return logger.info("request_started", **extra)


def log_response(
    logger: structlog.BoundLogger,
    status_code: int,
    duration_ms: float | None = None,
    size: int | None = None,
) -> None:
    """Log an HTTP response."""
    extra = {
        "http_status_code": status_code,
    }
    
    if duration_ms is not None:
        extra["duration_ms"] = round(duration_ms, 2)
    if size is not None:
        extra["response_size"] = size
    
    if 200 <= status_code < 300:
        logger.info("request_completed", **extra)
    elif 400 <= status_code < 500:
        logger.warning("client_error", **extra)
    else:
        logger.error("server_error", **extra)


def log_error(
    logger: structlog.BoundLogger,
    error: Exception,
    message: str | None = None,
    include_traceback: bool = True,
) -> None:
    """Log an error with structured information."""
    extra = {
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    
    if message:
        extra["message"] = message
    
    if include_traceback and hasattr(error, '__traceback__'):
        import traceback
        tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        if len(tb_str) > 2000:
            tb_str = tb_str[:2000] + "... [truncated]"
        extra["traceback"] = tb_str
    
    # Check for PeoplePayError
    from shared.errors import PeoplePayError
    if isinstance(error, PeoplePayError):
        extra["error_code"] = error.code
        extra["error_type"] = error.error_type
    
    logger.error("error", **extra)


def log_audit(
    logger: structlog.BoundLogger,
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: str | None = None,
    organization_id: str | None = None,
    success: bool = True,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log an audit event."""
    extra = {
        "audit_action": action,
        "audit_resource_type": resource_type,
        "audit_resource_id": resource_id,
        "audit_user_id": user_id,
        "audit_organization_id": organization_id,
        "audit_success": success,
    }
    
    if error:
        extra["audit_error"] = error
    if metadata:
        extra["audit_metadata"] = metadata
    
    if success:
        logger.info("audit_event", **extra)
    else:
        logger.warning("audit_failure", **extra)


def log_metric(
    logger: structlog.BoundLogger,
    name: str,
    value: float | int,
    tags: dict[str, Any] | None = None,
) -> None:
    """Log a metric for observability."""
    extra = {
        "metric_name": name,
        "metric_value": value,
    }
    
    if tags:
        extra["metric_tags"] = tags
    
    logger.info("metric", **extra)


# =============================================================================
# CONVENIENCE LOGGERS
# =============================================================================

# Create default logger
_default_logger: structlog.BoundLogger | None = None


def get_default_logger() -> structlog.BoundLogger:
    """Get the default logger, initializing if necessary."""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger()
    return _default_logger


# Module-level convenience functions
def debug(message: str, **kwargs: Any) -> None:
    """Log debug message."""
    get_default_logger().debug(message, **kwargs)


def info(message: str, **kwargs: Any) -> None:
    """Log info message."""
    get_default_logger().info(message, **kwargs)


def warning(message: str, **kwargs: Any) -> None:
    """Log warning message."""
    get_default_logger().warning(message, **kwargs)


def error(message: str, **kwargs: Any) -> None:
    """Log error message."""
    get_default_logger().error(message, **kwargs)


def exception(message: str, **kwargs: Any) -> None:
    """Log exception with traceback."""
    get_default_logger().exception(message, **kwargs)


# =============================================================================
# REQUEST CONTEXT MANAGEMENT
# =============================================================================

class RequestContext:
    """Context manager for request-scoped logging."""
    
    def __init__(self, request_id: str | None = None, **context_kw: Any):
        self.request_id = request_id or str(uuid4())
        self.context = LogContext(request_id=self.request_id, **context_kw)
        self._previous_context: LogContext | None = None
    
    def __enter__(self) -> LogContext:
        self._previous_context = get_context()
        set_context(self.context)
        return self.context
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._previous_context is not None:
            set_context(self._previous_context)
        else:
            set_context(None)


def with_request_context(request_id: str | None = None, **kwargs: Any):
    """Context manager for adding request context to logs."""
    return RequestContext(request_id=request_id, **kwargs)
