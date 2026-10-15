"""Authentication and authorization errors."""

from datetime import datetime
from shared.errors import PeoplePayError


class AuthError(PeoplePayError):
    """Base class for authentication errors."""
    
    def __init__(self, message: str = "Authentication error", code: str = "AUTH_000") -> None:
        super().__init__(message=message, code=code, error_type="authentication_error")


# =============================================================================
# AUTHENTICATION ERRORS
# =============================================================================

class AuthenticationError(AuthError):
    """Authentication failed."""
    
    def __init__(self, message: str = "Authentication failed", code: str = "AUTH_001") -> None:
        super().__init__(message=message, code=code, error_type="authentication_error")


class InvalidCredentialsError(AuthenticationError):
    """Invalid credentials provided."""
    
    def __init__(self, message: str = "Invalid credentials") -> None:
        super().__init__(message=message, code="AUTH_002")


class UserNotFoundError(AuthenticationError):
    """User not found."""
    
    def __init__(self, identifier: str, is_email: bool = False) -> None:
        message = f"User not found: {identifier}"
        if is_email:
            message = f"No user found with email: {identifier}"
        super().__init__(message=message, code="AUTH_003")


class UserAlreadyExistsError(AuthError):
    """User already exists."""
    
    def __init__(self, identifier: str, is_email: bool = False) -> None:
        message = f"User already exists: {identifier}"
        if is_email:
            message = f"A user already exists with email: {identifier}"
        super().__init__(message=message, code="AUTH_004")


class InvalidTokenError(AuthenticationError):
    """Invalid authentication token."""
    
    def __init__(self, message: str = "Invalid token") -> None:
        super().__init__(message=message, code="AUTH_005")


class TokenExpiredError(AuthenticationError):
    """Token has expired."""
    
    def __init__(self, message: str = "Token has expired") -> None:
        super().__init__(message=message, code="AUTH_006")


class TokenRevokedError(AuthenticationError):
    """Token has been revoked."""
    
    def __init__(self, message: str = "Token has been revoked") -> None:
        super().__init__(message=message, code="AUTH_007")


# =============================================================================
# AUTHORIZATION ERRORS
# =============================================================================

class AuthorizationError(AuthError):
    """Authorization failed."""
    
    def __init__(self, message: str = "Authorization failed", code: str = "AUTH_100") -> None:
        super().__init__(message=message, code=code, error_type="authorization_error")


class PermissionDeniedError(AuthorizationError):
    """Permission denied."""
    
    def __init__(
        self,
        permission: str | None = None,
        user_id: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        message = "Permission denied"
        if permission:
            message += f": {permission}"
        super().__init__(message=message, code="AUTH_101")
        self.permission = permission
        self.user_id = user_id
        self.resource_id = resource_id


class InsufficientPrivilegesError(AuthorizationError):
    """User doesn't have sufficient privileges."""
    
    def __init__(self, message: str = "Insufficient privileges") -> None:
        super().__init__(message=message, code="AUTH_102")


class AccessDeniedError(AuthorizationError):
    """Access to resource denied."""
    
    def __init__(self, resource_type: str, resource_id: str, reason: str | None = None) -> None:
        message = f"Access denied to {resource_type}: {resource_id}"
        if reason:
            message += f" - {reason}"
        super().__init__(message=message, code="AUTH_103")


# =============================================================================
# SESSION ERRORS
# =============================================================================

class SessionError(AuthError):
    """Session-related error."""
    
    def __init__(self, message: str = "Session error", code: str = "AUTH_200") -> None:
        super().__init__(message=message, code=code, error_type="session_error")


class SessionInvalidError(SessionError):
    """Session is invalid."""
    
    def __init__(self, message: str = "Invalid session") -> None:
        super().__init__(message=message, code="AUTH_201")


class SessionExpiredError(SessionError):
    """Session has expired."""
    
    def __init__(self, message: str = "Session has expired") -> None:
        super().__init__(message=message, code="AUTH_202")


class SessionNotFoundError(SessionError):
    """Session not found."""
    
    def __init__(self, session_id: str) -> None:
        super().__init__(message=f"Session not found: {session_id}", code="AUTH_203")


class TooManySessionsError(SessionError):
    """Too many active sessions."""
    
    def __init__(self, max_sessions: int) -> None:
        super().__init__(
            message=f"Maximum {max_sessions} sessions reached",
            code="AUTH_204"
        )


# =============================================================================
# PASSWORD ERRORS
# =============================================================================

class PasswordError(AuthError):
    """Password-related error."""
    
    def __init__(self, message: str = "Password error", code: str = "AUTH_300") -> None:
        super().__init__(message=message, code=code, error_type="password_error")


class PasswordTooWeakError(PasswordError):
    """Password doesn't meet requirements."""
    
    def __init__(self, reasons: list[str] | None = None) -> None:
        message = "Password is too weak"
        if reasons:
            message += f": {', '.join(reasons)}"
        super().__init__(message=message, code="AUTH_301")


class PasswordChangeRequiredError(PasswordError):
    """Password change is required."""
    
    def __init__(self, message: str = "Password change required") -> None:
        super().__init__(message=message, code="AUTH_302")


class InvalidPasswordError(PasswordError):
    """Invalid password provided."""
    
    def __init__(self, message: str = "Invalid password") -> None:
        super().__init__(message=message, code="AUTH_303")


# =============================================================================
# MFA ERRORS
# =============================================================================

class MFAError(AuthError):
    """Multi-factor authentication error."""
    
    def __init__(self, message: str = "MFA error", code: str = "AUTH_400") -> None:
        super().__init__(message=message, code=code, error_type="mfa_error")


class MFARequiredError(MFAError):
    """MFA is required but not completed."""
    
    def __init__(self, message: str = "Multi-factor authentication required") -> None:
        super().__init__(message=message, code="AUTH_401")


class MFAInvalidCodeError(MFAError):
    """Invalid MFA code provided."""
    
    def __init__(self, message: str = "Invalid MFA code") -> None:
        super().__init__(message=message, code="AUTH_402")


class MFAExpiredCodeError(MFAError):
    """MFA code has expired."""
    
    def __init__(self, message: str = "MFA code has expired") -> None:
        super().__init__(message=message, code="AUTH_403")


class MFAMethodNotConfiguredError(MFAError):
    """MFA method not configured."""
    
    def __init__(self, method: str) -> None:
        super().__init__(
            message=f"MFA method '{method}' is not configured",
            code="AUTH_404"
        )


# =============================================================================
# ACCOUNT ERRORS
# =============================================================================

class AccountError(AuthError):
    """Account-related error."""
    
    def __init__(self, message: str = "Account error", code: str = "AUTH_500") -> None:
        super().__init__(message=message, code=code, error_type="account_error")


class AccountLockedError(AccountError):
    """Account is locked."""
    
    def __init__(self, message: str = "Account is locked", until: datetime | None = None) -> None:
        if until:
            message = f"Account is locked until {until}"
        super().__init__(message=message, code="AUTH_501")


class AccountSuspendedError(AccountError):
    """Account is suspended."""
    
    def __init__(self, message: str = "Account is suspended") -> None:
        super().__init__(message=message, code="AUTH_502")


class AccountInactiveError(AccountError):
    """Account is inactive."""
    
    def __init__(self, message: str = "Account is inactive") -> None:
        super().__init__(message=message, code="AUTH_503")


class AccountPendingError(AccountError):
    """Account is pending activation."""
    
    def __init__(self, message: str = "Account is pending activation") -> None:
        super().__init__(message=message, code="AUTH_504")


# =============================================================================
# ORGANIZATION ERRORS
# =============================================================================

class OrganizationError(AuthError):
    """Organization-related error."""
    
    def __init__(self, message: str = "Organization error", code: str = "AUTH_600") -> None:
        super().__init__(message=message, code=code, error_type="organization_error")


class OrganizationNotFoundError(OrganizationError):
    """Organization not found."""
    
    def __init__(self, organization_id: str) -> None:
        super().__init__(
            message=f"Organization not found: {organization_id}",
            code="AUTH_601"
        )


class OrganizationAlreadyExistsError(OrganizationError):
    """Organization already exists."""
    
    def __init__(self, name: str) -> None:
        super().__init__(
            message=f"Organization '{name}' already exists",
            code="AUTH_602"
        )


class NotOrganizationMemberError(OrganizationError):
    """User is not a member of the organization."""
    
    def __init__(self, user_id: str, organization_id: str) -> None:
        super().__init__(
            message=f"User {user_id} is not a member of organization {organization_id}",
            code="AUTH_603"
        )


class OrganizationSuspendedError(OrganizationError):
    """Organization is suspended."""
    
    def __init__(self, organization_id: str) -> None:
        super().__init__(
            message=f"Organization {organization_id} is suspended",
            code="AUTH_604"
        )
