"""Standard error handling for PeoplePay 360.

This module provides a consistent error handling pattern across all services.
All errors should derive from PeoplePayError for proper typing and handling.
"""

from __future__ import annotations

import traceback
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.schemas import ErrorCode, ErrorResponse


class PeoplePayError(Exception):
    """Base exception for all PeoplePay errors.
    
    All service-specific errors should inherit from this class for consistent
    error handling and logging.
    """
    
    def __init__(
        self,
        message: str,
        code: str = "E000",
        error_type: str = "internal_error",
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.error_type = error_type
        self.details = details or {}
        self.cause = cause
        self.stack_trace = traceback.format_stack()
    
    def to_error_response(self) -> "ErrorResponse":
        """Convert to standard error response schema."""
        from shared.schemas import ErrorCode, ErrorResponse
        
        # Map code string to ErrorCode enum
        try:
            error_code = ErrorCode(self.code)
        except ValueError:
            error_code = ErrorCode.INTERNAL_ERROR
        
        return ErrorResponse(
            error=self.error_type,
            code=error_code,
            message=self.message,
            details=self.details if self.details else None,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "error_type": self.error_type,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
    
    def __str__(self) -> str:
        return f"[{self.code}] {self.error_type}: {self.message}"
    
    def __repr__(self) -> str:
        return f"PeoplePayError({self.code!r}, {self.error_type!r}, {self.message!r})"


# =============================================================================
# AUTHENTICATION ERRORS
# =============================================================================

class AuthenticationError(PeoplePayError):
    """Authentication failed or credentials are invalid."""
    
    def __init__(
        self,
        message: str = "Authentication failed",
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="E401",
            error_type="unauthorized",
            details=details,
            cause=cause,
        )


class TokenExpiredError(AuthenticationError):
    """Authentication token has expired."""
    
    def __init__(self, message: str = "Token has expired") -> None:
        super().__init__(message=message, code="E401_EXPIRED")


class TokenInvalidError(AuthenticationError):
    """Authentication token is invalid."""
    
    def __init__(self, message: str = "Invalid authentication token") -> None:
        super().__init__(message=message, code="E401_INVALID")


class CredentialsInvalidError(AuthenticationError):
    """Provided credentials are invalid."""
    
    def __init__(self, message: str = "Invalid credentials") -> None:
        super().__init__(message=message, code="E401_CREDENTIALS")


# =============================================================================
# AUTHORIZATION ERRORS
# =============================================================================

class AuthorizationError(PeoplePayError):
    """Authorization failed - user lacks required permissions."""
    
    def __init__(
        self,
        message: str = "Authorization failed",
        permission: str | None = None,
        user_id: str | None = None,
        resource_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        details = {}
        if permission:
            details["required_permission"] = permission
        if user_id:
            details["user_id"] = user_id
        if resource_id:
            details["resource_id"] = resource_id
        
        super().__init__(
            message=message,
            code="E403",
            error_type="forbidden",
            details=details,
            cause=cause,
        )
        self.permission = permission
        self.user_id = user_id
        self.resource_id = resource_id


class PermissionDeniedError(AuthorizationError):
    """User does not have the required permission."""
    
    def __init__(
        self,
        permission: str,
        user_id: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        message = f"Permission denied: {permission}"
        super().__init__(
            message=message,
            permission=permission,
            user_id=user_id,
            resource_id=resource_id,
        )


class AccessDeniedError(AuthorizationError):
    """Access to resource is denied."""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        user_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        message = f"Access denied to {resource_type} {resource_id}"
        if reason:
            message += f": {reason}"
        super().__init__(
            message=message,
            user_id=user_id,
            resource_id=resource_id,
        )


class OwnershipRequiredError(AuthorizationError):
    """User does not own the resource."""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        user_id: str | None = None,
        owner_id: str | None = None,
    ) -> None:
        message = f"Ownership required for {resource_type} {resource_id}"
        details = {"resource_type": resource_type, "resource_id": resource_id}
        if owner_id:
            details["owner_id"] = owner_id
        super().__init__(
            message=message,
            user_id=user_id,
            resource_id=resource_id,
            details=details,
        )


# =============================================================================
# VALIDATION ERRORS
# =============================================================================

class ValidationError(PeoplePayError):
    """Input validation failed."""
    
    def __init__(
        self,
        message: str = "Validation failed",
        field: str | None = None,
        value: Any = None,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        error_details = details or {}
        if field:
            error_details["field"] = field
        if value is not None:
            # Don't include large values in error responses
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:100] + "..."
            error_details["value"] = value_str
        
        super().__init__(
            message=message,
            code="E400",
            error_type="validation_error",
            details=error_details,
            cause=cause,
        )
        self.field = field
        self.value = value


class RequiredFieldError(ValidationError):
    """Required field is missing."""
    
    def __init__(self, field: str, message: str | None = None) -> None:
        super().__init__(
            message=message or f"Required field '{field}' is missing",
            field=field,
        )


class InvalidFormatError(ValidationError):
    """Field has invalid format."""
    
    def __init__(self, field: str, expected_format: str, value: Any = None) -> None:
        message = f"Field '{field}' has invalid format. Expected: {expected_format}"
        super().__init__(message=message, field=field, value=value)


class RangeError(ValidationError):
    """Field value is out of range."""
    
    def __init__(self, field: str, min_val: Any | None = None, max_val: Any | None = None, value: Any = None) -> None:
        if min_val is not None and max_val is not None:
            message = f"Field '{field}' must be between {min_val} and {max_val}"
        elif min_val is not None:
            message = f"Field '{field}' must be at least {min_val}"
        elif max_val is not None:
            message = f"Field '{field}' must be at most {max_val}"
        else:
            message = f"Field '{field}' is out of range"
        super().__init__(message=message, field=field, value=value)


# =============================================================================
# RESOURCE ERRORS
# =============================================================================

class NotFoundError(PeoplePayError):
    """Requested resource was not found."""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message=message or f"{resource_type} not found: {resource_id}",
            code="E404",
            error_type="not_found",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )
        self.resource_type = resource_type
        self.resource_id = resource_id


class ConflictError(PeoplePayError):
    """Resource conflict - duplicate or incompatible state."""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: str | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        error_details["resource_type"] = resource_type
        if resource_id:
            error_details["resource_id"] = resource_id
        
        super().__init__(
            message=message or f"Conflict: {resource_type} already exists",
            code="E409",
            error_type="conflict",
            details=error_details,
        )
        self.resource_type = resource_type
        self.resource_id = resource_id


class AlreadyExistsError(ConflictError):
    """Resource already exists."""
    
    def __init__(self, resource_type: str, resource_id: str, identifier: str) -> None:
        message = f"{resource_type} with {identifier} already exists"
        super().__init__(
            resource_type=resource_type,
            resource_id=resource_id,
            message=message,
        )


class InvalidStateError(PeoplePayError):
    """Resource is in an invalid state for the requested operation."""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        current_state: str,
        required_state: str | None = None,
        operation: str | None = None,
    ) -> None:
        if required_state:
            message = f"Cannot {operation or 'perform operation'}: {resource_type} {resource_id} is in state '{current_state}', requires '{required_state}'"
        else:
            message = f"Cannot perform operation: {resource_type} {resource_id} is in invalid state '{current_state}'"
        
        super().__init__(
            message=message,
            code="E409_STATE",
            error_type="invalid_state",
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "current_state": current_state,
                "required_state": required_state,
                "operation": operation,
            },
        )


# =============================================================================
# PAYMENT ERRORS
# =============================================================================

class PaymentError(PeoplePayError):
    """Base class for payment-related errors."""
    
    def __init__(
        self,
        message: str,
        payment_id: str | None = None,
        order_id: str | None = None,
        code: str = "E_PAYMENT",
        cause: Exception | None = None,
    ) -> None:
        details = {}
        if payment_id:
            details["payment_id"] = payment_id
        if order_id:
            details["order_id"] = order_id
        
        super().__init__(
            message=message,
            code=code,
            error_type="payment_error",
            details=details,
            cause=cause,
        )


class PaymentFailedError(PaymentError):
    """Payment processing failed."""
    
    def __init__(
        self,
        message: str = "Payment processing failed",
        payment_id: str | None = None,
        order_id: str | None = None,
        reason: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            payment_id=payment_id,
            order_id=order_id,
            code="E_PAYMENT_FAILED",
            cause=cause,
        )
        self.reason = reason


class PaymentAuthorizationError(PaymentError):
    """Payment authorization failed or was denied."""
    
    def __init__(
        self,
        message: str = "Payment authorization denied",
        payment_id: str | None = None,
        order_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            payment_id=payment_id,
            order_id=order_id,
            code="E_PAYMENT_AUTH",
        )
        self.reason = reason


class InsufficientFundsError(PaymentError):
    """Insufficient funds for the payment."""
    
    def __init__(
        self,
        amount: int,
        currency: str,
        available: int | None = None,
        payment_id: str | None = None,
    ) -> None:
        available_str = f" (available: {available} {currency})" if available is not None else ""
        message = f"Insufficient funds: {amount} {currency} required{available_str}"
        super().__init__(message=message, payment_id=payment_id, code="E_PAYMENT_INSUFFICIENT")


class BudgetExceededError(PaymentError):
    """Payment exceeds budget limit."""
    
    def __init__(
        self,
        amount: int,
        currency: str,
        budget_limit: int,
        payment_id: str | None = None,
        order_id: str | None = None,
    ) -> None:
        message = f"Budget exceeded: {amount} {currency} exceeds limit of {budget_limit} {currency}"
        super().__init__(
            message=message,
            payment_id=payment_id,
            order_id=order_id,
            code="E_PAYMENT_BUDGET",
        )


class ApprovalRequiredError(PaymentError):
    """Payment requires human approval."""
    
    def __init__(
        self,
        message: str = "Human approval required for this payment",
        payment_id: str | None = None,
        order_id: str | None = None,
        approver: str | None = None,
    ) -> None:
        details = {}
        if approver:
            details["required_approver"] = approver
        super().__init__(
            message=message,
            payment_id=payment_id,
            order_id=order_id,
            code="E_PAYMENT_APPROVAL",
            details=details,
        )


# =============================================================================
# WORKFLOW ERRORS
# =============================================================================

class WorkflowError(PeoplePayError):
    """Base class for workflow-related errors."""
    
    def __init__(
        self,
        message: str,
        workflow_id: str | None = None,
        task_id: str | None = None,
        code: str = "E_WORKFLOW",
        cause: Exception | None = None,
    ) -> None:
        details = {}
        if workflow_id:
            details["workflow_id"] = workflow_id
        if task_id:
            details["task_id"] = task_id
        
        super().__init__(
            message=message,
            code=code,
            error_type="workflow_error",
            details=details,
            cause=cause,
        )


class WorkflowTimeoutError(WorkflowError):
    """Workflow execution timed out."""
    
    def __init__(
        self,
        workflow_id: str,
        timeout_seconds: float,
        task_id: str | None = None,
    ) -> None:
        message = f"Workflow {workflow_id} timed out after {timeout_seconds} seconds"
        super().__init__(
            message=message,
            workflow_id=workflow_id,
            task_id=task_id,
            code="E_WORKFLOW_TIMEOUT",
        )


class WorkflowCancelledError(WorkflowError):
    """Workflow was cancelled."""
    
    def __init__(self, workflow_id: str, reason: str | None = None) -> None:
        message = f"Workflow {workflow_id} was cancelled"
        if reason:
            message += f": {reason}"
        super().__init__(
            message=message,
            workflow_id=workflow_id,
            code="E_WORKFLOW_CANCELLED",
        )


class MaxRetriesExceededError(WorkflowError):
    """Maximum retry attempts exceeded."""
    
    def __init__(
        self,
        workflow_id: str,
        task_id: str,
        max_retries: int,
        cause: Exception | None = None,
    ) -> None:
        message = f"Task {task_id} in workflow {workflow_id} exceeded {max_retries} retries"
        super().__init__(
            message=message,
            workflow_id=workflow_id,
            task_id=task_id,
            code="E_WORKFLOW_RETRIES",
            cause=cause,
        )


# =============================================================================
# AGENT ERRORS
# =============================================================================

class AgentError(PeoplePayError):
    """Base class for agent-related errors."""
    
    def __init__(
        self,
        message: str,
        agent_id: str | None = None,
        tool_name: str | None = None,
        code: str = "E_AGENT",
        cause: Exception | None = None,
    ) -> None:
        details = {}
        if agent_id:
            details["agent_id"] = agent_id
        if tool_name:
            details["tool_name"] = tool_name
        
        super().__init__(
            message=message,
            code=code,
            error_type="agent_error",
            details=details,
            cause=cause,
        )


class ToolExecutionError(AgentError):
    """Tool execution failed."""
    
    def __init__(
        self,
        tool_name: str,
        agent_id: str | None = None,
        error: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        message = f"Tool '{tool_name}' execution failed"
        if error:
            message += f": {error}"
        super().__init__(
            message=message,
            agent_id=agent_id,
            tool_name=tool_name,
            code="E_AGENT_TOOL",
            cause=cause,
        )


class ToolPermissionError(AgentError):
    """Agent lacks permission to use a tool."""
    
    def __init__(
        self,
        tool_name: str,
        agent_id: str,
        required_permission: str | None = None,
    ) -> None:
        message = f"Agent '{agent_id}' cannot use tool '{tool_name}'"
        if required_permission:
            message += f" (requires: {required_permission})"
        super().__init__(
            message=message,
            agent_id=agent_id,
            tool_name=tool_name,
            code="E_AGENT_PERMISSION",
        )


# =============================================================================
# EVIDENCE ERRORS
# =============================================================================

class EvidenceError(PeoplePayError):
    """Base class for evidence-related errors."""
    
    def __init__(
        self,
        message: str,
        evidence_id: str | None = None,
        source_id: str | None = None,
        code: str = "E_EVIDENCE",
        cause: Exception | None = None,
    ) -> None:
        details = {}
        if evidence_id:
            details["evidence_id"] = evidence_id
        if source_id:
            details["source_id"] = source_id
        
        super().__init__(
            message=message,
            code=code,
            error_type="evidence_error",
            details=details,
            cause=cause,
        )


class EvidenceFreshnessError(EvidenceError):
    """Evidence is too old or stale."""
    
    def __init__(
        self,
        evidence_id: str,
        age_hours: float,
        max_age_hours: float,
    ) -> None:
        message = f"Evidence {evidence_id} is {age_hours:.1f} hours old, maximum allowed is {max_age_hours:.1f} hours"
        super().__init__(
            message=message,
            evidence_id=evidence_id,
            code="E_EVIDENCE_FRESHNESS",
        )


class EvidenceContradictionError(EvidenceError):
    """Evidence contradicts existing evidence."""
    
    def __init__(
        self,
        evidence_id: str,
        contradicts_id: str,
        field: str | None = None,
    ) -> None:
        message = f"Evidence {evidence_id} contradicts {contradicts_id}"
        if field:
            message += f" on field '{field}'"
        super().__init__(
            message=message,
            evidence_id=evidence_id,
            code="E_EVIDENCE_CONTRADICTION",
            details={"contradicts_id": contradicts_id, "field": field},
        )


# =============================================================================
# WEBHOOK ERRORS
# =============================================================================

class WebhookError(PeoplePayError):
    """Base class for webhook-related errors."""
    
    def __init__(
        self,
        message: str,
        webhook_id: str | None = None,
        event_type: str | None = None,
        code: str = "E_WEBHOOK",
        cause: Exception | None = None,
    ) -> None:
        details = {}
        if webhook_id:
            details["webhook_id"] = webhook_id
        if event_type:
            details["event_type"] = event_type
        
        super().__init__(
            message=message,
            code=code,
            error_type="webhook_error",
            details=details,
            cause=cause,
        )


class WebhookSignatureError(WebhookError):
    """Webhook signature verification failed."""
    
    def __init__(
        self,
        webhook_id: str,
        expected_signature: str,
        actual_signature: str | None = None,
    ) -> None:
        message = f"Webhook {webhook_id} signature verification failed"
        details = {
            "webhook_id": webhook_id,
            "expected_signature": expected_signature[:20] + "..." if len(expected_signature) > 20 else expected_signature,
        }
        if actual_signature:
            details["actual_signature"] = actual_signature[:20] + "..." if len(actual_signature) > 20 else actual_signature
        
        super().__init__(
            message=message,
            webhook_id=webhook_id,
            code="E_WEBHOOK_SIGNATURE",
            details=details,
        )


class WebhookDuplicateError(WebhookError):
    """Duplicate webhook event detected."""
    
    def __init__(
        self,
        event_id: str,
        webhook_id: str | None = None,
        first_received: datetime | None = None,
    ) -> None:
        message = f"Duplicate webhook event: {event_id}"
        details = {"event_id": event_id}
        if first_received:
            details["first_received"] = first_received.isoformat()
        
        super().__init__(
            message=message,
            webhook_id=webhook_id,
            code="E_WEBHOOK_DUPLICATE",
            details=details,
        )


# =============================================================================
# RATE LIMIT ERRORS
# =============================================================================

class RateLimitError(PeoplePayError):
    """Rate limit exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        limit: int | None = None,
        window_seconds: int | None = None,
        retry_after: int | None = None,
        user_id: str | None = None,
    ) -> None:
        details = {}
        if limit is not None:
            details["limit"] = limit
        if window_seconds is not None:
            details["window_seconds"] = window_seconds
        if retry_after is not None:
            details["retry_after"] = retry_after
        if user_id:
            details["user_id"] = user_id
        
        super().__init__(
            message=message,
            code="E429",
            error_type="rate_limit_exceeded",
            details=details,
        )


# =============================================================================
# SERVICE ERRORS
# =============================================================================

class ServiceUnavailableError(PeoplePayError):
    """Service is temporarily unavailable."""
    
    def __init__(
        self,
        service: str,
        reason: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        message = f"Service '{service}' is unavailable"
        if reason:
            message += f": {reason}"
        
        details = {"service": service}
        if retry_after is not None:
            details["retry_after"] = retry_after
        
        super().__init__(
            message=message,
            code="E503",
            error_type="service_unavailable",
            details=details,
        )


class ServiceNotConfiguredError(PeoplePayError):
    """Required service is not configured."""
    
    def __init__(self, service: str, required_setting: str | None = None) -> None:
        message = f"Service '{service}' is not configured"
        if required_setting:
            message += f" (missing: {required_setting})"
        
        super().__init__(
            message=message,
            code="E503_CONFIG",
            error_type="not_configured",
            details={"service": service, "missing_setting": required_setting},
        )
