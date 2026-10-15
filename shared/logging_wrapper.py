"""Logging wrapper that falls back to simple logging when structlog is unavailable."""

import sys

try:
    from shared.logging import (
        get_logger,
        setup_logging,
        LogContext,
        get_context,
        set_context,
    )
    USING_STRUCTLOG = True
except ImportError:
    try:
        from shared.logging_simple import (
            get_logger,
            setup_logging,
            LogContext,
            get_context,
            set_context,
        )
        USING_STRUCTLOG = False
    except ImportError:
        # Absolute fallback
        import logging
        
        class LogContext:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
            
            def to_dict(self):
                return self.__dict__
        
        def get_context():
            return LogContext()
        
        def set_context(context):
            pass
        
        def get_logger(name=None):
            return logging.getLogger(name or "peoplepay")
        
        def setup_logging(level=None, format_type="text", **kwargs):
            logging.basicConfig(
                level=getattr(logging, level or "INFO", logging.INFO),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            )
            return logging.getLogger()
        
        USING_STRUCTLOG = False

# Re-export
__all__ = [
    "get_logger",
    "setup_logging",
    "LogContext",
    "get_context",
    "set_context",
    "USING_STRUCTLOG",
]
