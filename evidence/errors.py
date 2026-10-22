"""
Evidence and Provenance Error Definitions
"""

from typing import Any, Dict, List, Optional


class EvidenceError(Exception):
    """Base exception for evidence-related errors."""
    
    def __init__(self, message: str, error_type: str = "evidence_error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.error_type,
            "message": self.message,
            "details": self.details,
        }


class EvidenceNotFoundError(EvidenceError):
    """Raised when evidence cannot be found."""
    
    def __init__(self, evidence_id: str, message: Optional[str] = None):
        self.evidence_id = evidence_id
        msg = message or f"Evidence with ID '{evidence_id}' not found"
        super().__init__(msg, error_type="evidence_not_found", details={"evidence_id": evidence_id})


class SourceNotFoundError(EvidenceError):
    """Raised when a source cannot be found."""
    
    def __init__(self, source_id: str, message: Optional[str] = None):
        self.source_id = source_id
        msg = message or f"Source with ID '{source_id}' not found"
        super().__init__(msg, error_type="source_not_found", details={"source_id": source_id})


class VerificationError(EvidenceError):
    """Raised when evidence verification fails."""
    
    def __init__(self, message: str, verification_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.verification_id = verification_id
        super().__init__(message, error_type="verification_failed", 
                        details={"verification_id": verification_id, **(details or {})})


class SourceUnavailableError(EvidenceError):
    """Raised when a source is temporarily unavailable."""
    
    def __init__(self, source_id: str, message: Optional[str] = None, retry_after: Optional[int] = None):
        self.source_id = source_id
        self.retry_after = retry_after
        msg = message or f"Source '{source_id}' is currently unavailable"
        super().__init__(msg, error_type="source_unavailable", 
                        details={"source_id": source_id, "retry_after": retry_after})


class IntegrityError(EvidenceError):
    """Raised when evidence integrity is compromised."""
    
    def __init__(self, evidence_id: str, message: Optional[str] = None, expected_hash: Optional[str] = None, actual_hash: Optional[str] = None):
        self.evidence_id = evidence_id
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        msg = message or f"Evidence '{evidence_id}' integrity check failed"
        super().__init__(msg, error_type="integrity_error", 
                        details={
                            "evidence_id": evidence_id,
                            "expected_hash": expected_hash,
                            "actual_hash": actual_hash,
                        })


class ContradictionError(EvidenceError):
    """Raised when a contradiction is detected but not resolved."""
    
    def __init__(self, contradiction_id: str, message: Optional[str] = None, severity: str = "high"):
        self.contradiction_id = contradiction_id
        self.severity = severity
        msg = message or f"Unresolved contradiction detected: {contradiction_id}"
        super().__init__(msg, error_type="contradiction_detected", 
                        details={"contradiction_id": contradiction_id, "severity": severity})


class ClaimExtractionError(EvidenceError):
    """Raised when claim extraction fails."""
    
    def __init__(self, evidence_id: str, message: Optional[str] = None):
        self.evidence_id = evidence_id
        msg = message or f"Failed to extract claims from evidence '{evidence_id}'"
        super().__init__(msg, error_type="claim_extraction_failed", 
                        details={"evidence_id": evidence_id})


class StorageError(EvidenceError):
    """Raised when evidence storage operations fail."""
    
    def __init__(self, message: str, operation: str = "unknown", details: Optional[Dict[str, Any]] = None):
        self.operation = operation
        super().__init__(message, error_type="storage_error", 
                        details={"operation": operation, **(details or {})})


class ProvenanceError(EvidenceError):
    """Raised when provenance tracking fails."""
    
    def __init__(self, message: str, action_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.action_id = action_id
        super().__init__(message, error_type="provenance_error", 
                        details={"action_id": action_id, **(details or {})})


# Ensure all error types are available
EvidenceException = EvidenceError
SourceException = SourceNotFoundError
VerificationException = VerificationError
