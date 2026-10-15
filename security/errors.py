"""Security Service Errors"""

class SecurityError(Exception):
    def __init__(self, message, code="SECURITY_ERROR"):
        super().__init__(message)
        self.code = code

class AuditError(SecurityError):
    def __init__(self, message):
        super().__init__(message, "AUDIT_ERROR")

class PolicyError(SecurityError):
    def __init__(self, message):
        super().__init__(message, "POLICY_ERROR")

class ScanError(SecurityError):
    def __init__(self, message):
        super().__init__(message, "SCAN_ERROR")

class RedactionError(SecurityError):
    def __init__(self, message):
        super().__init__(message, "REDACTION_ERROR")

class IncidentError(SecurityError):
    def __init__(self, message):
        super().__init__(message, "INCIDENT_ERROR")
