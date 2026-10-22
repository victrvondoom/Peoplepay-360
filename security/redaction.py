"""Data Redaction"""
import re
import threading
from typing import Any, Dict, List

from security.errors import RedactionError


# Default redaction patterns
REDACTION_PATTERNS = [
    (re.compile(r"(?:password|passwd|secret)\s*[:=]\s*['\"]?[^'\"\s]+['\"]?", re.IGNORECASE), "[REDACTED_PASSWORD]"),
    (re.compile(r"(?:api_key|apikey|token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE), "[REDACTED_TOKEN]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", re.IGNORECASE), "[REDACTED_CARD]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b", re.IGNORECASE), "[REDACTED_SSN]"),
]


class SecretRedactor:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._patterns = list(REDACTION_PATTERNS)
                cls._instance._lock = threading.Lock()
            return cls._instance
    
    def redact(self, data: Any) -> Any:
        """Redact sensitive data from any input."""
        if isinstance(data, str):
            return self._redact_string(data)
        elif isinstance(data, dict):
            return self._redact_dict(data)
        elif isinstance(data, list):
            return [self.redact(item) for item in data]
        else:
            return data
    
    def _redact_string(self, data: str) -> str:
        """Redact sensitive data from a string."""
        result = data
        
        with self._lock:
            patterns = list(self._patterns)
        
        for pattern, replacement in patterns:
            result = pattern.sub(replacement, result)
        
        return result
    
    def _redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive data from a dictionary."""
        result = {}
        
        for key, value in data.items():
            # Check if key itself is sensitive
            key_lower = key.lower()
            if any(s in key_lower for s in ["password", "secret", "token", "api_key"]):
                result[key] = "[REDACTED]"
                continue
            
            # Redact the value
            if isinstance(value, str):
                result[key] = self._redact_string(value)
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value)
            elif isinstance(value, list):
                result[key] = [self.redact(item) for item in value]
            else:
                result[key] = value
        
        return result
    
    def add_pattern(self, pattern: str, replacement: str):
        """Add a redaction pattern."""
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            with self._lock:
                self._patterns.append((compiled, replacement))
        except re.error as e:
            raise RedactionError(f"Invalid pattern: {e}")


def get_redactor():
    return SecretRedactor()


def reset_redactor():
    SecretRedactor._instance = None


def redact_data(data):
    """Redact sensitive data from any input."""
    return get_redactor().redact(data)
