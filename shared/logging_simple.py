"""Simplified logging for PeoplePay 360 (fallback without structlog).

This module provides basic logging functionality when structlog is not available.
"""

import logging
import sys
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


# =============================================================================
# LOG CONTEXT
# =============================================================================

@dataclass
class LogContext:
    """Contextual information to include in log entries."""
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    service: Optional[str] = None
    session_id: Optional[str] = None
    workflow_id: Optional[str] = None
    task_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


# Thread-local and async-local context storage
_context_var: ContextVar[Optional[LogContext]] = ContextVar('log_context', default=None)
_thread_local = threading.local()


def get_context() -> LogContext:
    """Get the current log context."""
    ctx = _context_var.get()
    if ctx:
        return ctx
    if hasattr(_thread_local, 'context'):
        return _thread_local.context
    return LogContext()


def set_context(context: Optional[LogContext] = None) -> None:
    """Set the current log context."""
    if context is None:
        context = LogContext()
    _context_var.set(context)
    _thread_local.context = context


# =============================================================================
# LOGGER SETUP
# =============================================================================

def setup_logging(
    level: Optional[str] = None,
    format_type: str = "text",
    log_file: Optional[str] = None,
    service_name: Optional[str] = None,
    include_timestamp: bool = True,
):
    """Set up basic logging."""
    # Determine log level
    if level is None:
        level = "INFO"
    
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure standard library logging
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        format=log_format,
    )
    
    # Set service name if provided
    if service_name:
        set_context(LogContext(service=service_name))
    
    return logging.getLogger()


def get_logger(name: Optional[str] = None):
    """Get a logger with the given name."""
    return logging.getLogger(name or "peoplepay")


# =============================================================================
# LOG HELPERS
# =============================================================================

def log_error(
    logger,
    error: Exception,
    message: Optional[str] = None,
    include_traceback: bool = True,
) -> None:
    """Log an error with structured information."""
    logger.error(
        f"Error: {type(error).__name__}: {str(error)}",
        extra={
            "error_type": type(error).__name__,
            "error_message": str(error),
        },
    )
    if include_traceback and hasattr(error, '__traceback__'):
        import traceback
        tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        logger.error(f"Traceback:\n{tb_str}")


def log_audit(
    logger,
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """Log an audit event."""
    status = "SUCCESS" if success else "FAILURE"
    logger.info(
        f"AUDIT: {action} on {resource_type}:{resource_id} - {status}",
        extra={
            "audit_action": action,
            "audit_resource_type": resource_type,
            "audit_resource_id": resource_id,
            "audit_status": status,
            "audit_user_id": user_id,
            "audit_organization_id": organization_id,
            "audit_error": error,
        },
    )


# =============================================================================
# CONVENIENCE LOGGERS
# =============================================================================

_default_logger = None


def get_default_logger():
    """Get the default logger, initializing if necessary."""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger()
    return _default_logger
