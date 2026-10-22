"""Payment and commerce service errors."""

from datetime import datetime
from typing import Any

from shared.errors import PeoplePayError


# =============================================================================
# PAYMENT ERRORS
# =============================================================================

class PaymentError(PeoplePayError):
    """Base class for payment-related errors."""
    
    def __init__(
        self,
        message: str,
        code: str = "PAY_000",
        payment_id: str | None = None,
        order_id: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        error_details = details or {}
        if payment_id:
            error_details["payment_id"] = payment_id
        if order_id:
            error_details["order_id"] = order_id
        if reason:
            error_details["reason"] = reason
        
        super().__init__(
            message=message,
            code=code,
            error_type="payment_error",
            details=error_details if error_details else None,
            cause=cause,
        )
        self.payment_id = payment_id
        self.order_id = order_id
        self.reason = reason


class PaymentProcessingError(PaymentError):
    """Payment processing failed."""
    pass


class PaymentFailedError(PaymentError):
    """Payment failed."""
    
    def __init__(self, message: str = "Payment failed", reason: str | None = None, payment_id: str | None = None, order_id: str | None = None, cause: Exception | None = None) -> None:
        if reason and message == "Payment failed":
            message = f"{message}: {reason}"
        super().__init__(message=message, code="PAY_002", payment_id=payment_id, order_id=order_id, reason=reason, cause=cause)


class PaymentNotFoundError(PaymentError):
    """Payment not found."""
    
    def __init__(self, payment_id: str) -> None:
        super().__init__(message=f"Payment not found: {payment_id}", code="PAY_003", payment_id=payment_id)


class PaymentAlreadyProcessedError(PaymentError):
    """Payment was already processed."""
    
    def __init__(self, payment_id: str, current_status: str) -> None:
        super().__init__(
            message=f"Payment {payment_id} already processed with status: {current_status}",
            code="PAY_004",
            payment_id=payment_id,
            details={"current_status": current_status},
        )
        self.current_status = current_status


class InvalidPaymentAmountError(PaymentError):
    """Invalid payment amount."""
    pass


class CurrencyMismatchError(PaymentError):
    """Currency mismatch in payment."""
    
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            message=f"Currency mismatch: expected {expected}, got {actual}",
            code="PAY_006",
            details={"expected": expected, "actual": actual},
        )
        self.expected = expected
        self.actual = actual


# =============================================================================
# CHECKOUT ERRORS
# =============================================================================

class CheckoutError(PeoplePayError):
    """Base class for checkout errors."""
    
    def __init__(self, message: str = "Checkout error", code: str = "PAY_100", session_id: str | None = None, details: dict[str, Any] | None = None, cause: Exception | None = None) -> None:
        error_details = details or {}
        if session_id:
            error_details["session_id"] = session_id
        super().__init__(message=message, code=code, error_type="checkout_error", details=error_details if error_details else None, cause=cause)
        self.session_id = session_id


class CheckoutSessionNotFoundError(CheckoutError):
    """Checkout session not found."""
    
    def __init__(self, session_id: str) -> None:
        super().__init__(message=f"Checkout session not found: {session_id}", code="PAY_101", session_id=session_id)


class CheckoutSessionExpiredError(CheckoutError):
    """Checkout session expired."""
    
    def __init__(self, session_id: str, expired_at: datetime) -> None:
        super().__init__(
            message=f"Checkout session {session_id} expired at {expired_at.isoformat()}",
            code="PAY_102",
            session_id=session_id,
            details={"expired_at": expired_at.isoformat()},
        )
        self.expired_at = expired_at


class CheckoutSessionCancelledError(CheckoutError):
    """Checkout session was cancelled."""
    
    def __init__(self, session_id: str) -> None:
        super().__init__(message=f"Checkout session cancelled: {session_id}", code="PAY_103", session_id=session_id)


# =============================================================================
# APPROVAL ERRORS
# =============================================================================

class ApprovalError(PeoplePayError):
    """Base class for approval errors."""
    
    def __init__(self, message: str = "Approval error", code: str = "PAY_200", approval_id: str | None = None, payment_id: str | None = None, details: dict[str, Any] | None = None, cause: Exception | None = None) -> None:
        error_details = details or {}
        if approval_id:
            error_details["approval_id"] = approval_id
        if payment_id:
            error_details["payment_id"] = payment_id
        super().__init__(message=message, code=code, error_type="approval_error", details=error_details if error_details else None, cause=cause)
        self.approval_id = approval_id


class ApprovalRequiredError(ApprovalError):
    """Approval is required for this payment."""
    pass


class ApprovalDeniedError(ApprovalError):
    """Payment approval was denied."""
    
    def __init__(self, reason: str | None = None, approval_id: str | None = None) -> None:
        message = "Payment approval denied"
        if reason:
            message += f": {reason}"
        details = {"reason": reason} if reason else None
        super().__init__(message=message, code="PAY_202", approval_id=approval_id, details=details)


class ApprovalNotFoundError(ApprovalError):
    """Approval not found."""
    
    def __init__(self, approval_id: str) -> None:
        super().__init__(message=f"Approval not found: {approval_id}", code="PAY_203", approval_id=approval_id)


class ApprovalAlreadyUsedError(ApprovalError):
    """Approval was already used."""
    
    def __init__(self, approval_id: str) -> None:
        super().__init__(message=f"Approval {approval_id} was already used", code="PAY_204", approval_id=approval_id)


# =============================================================================
# WEBHOOK ERRORS
# =============================================================================

class WebhookError(PeoplePayError):
    """Base class for webhook errors."""
    
    def __init__(self, message: str = "Webhook error", code: str = "PAY_300", webhook_id: str | None = None, event_type: str | None = None, details: dict[str, Any] | None = None, cause: Exception | None = None) -> None:
        error_details = details or {}
        if webhook_id:
            error_details["webhook_id"] = webhook_id
        if event_type:
            error_details["event_type"] = event_type
        super().__init__(message=message, code=code, error_type="webhook_error", details=error_details if error_details else None, cause=cause)


class WebhookVerificationError(WebhookError):
    """Webhook signature verification failed."""
    pass


class WebhookAlreadyProcessedError(WebhookError):
    """Webhook event was already processed."""
    
    def __init__(self, event_id: str) -> None:
        super().__init__(message=f"Webhook event {event_id} already processed", code="PAY_302", details={"event_id": event_id})
        self.event_id = event_id


class InvalidWebhookPayloadError(WebhookError):
    """Invalid webhook payload."""
    
    def __init__(self, reason: str) -> None:
        super().__init__(message=f"Invalid webhook payload: {reason}", code="PAY_303", details={"reason": reason})


# =============================================================================
# IDEMPOTENCY ERRORS
# =============================================================================

class IdempotencyError(PeoplePayError):
    """Base class for idempotency errors."""
    
    def __init__(self, message: str = "Idempotency error", code: str = "PAY_400", idempotency_key: str | None = None, details: dict[str, Any] | None = None, cause: Exception | None = None) -> None:
        error_details = details or {}
        if idempotency_key:
            error_details["idempotency_key"] = idempotency_key
        super().__init__(message=message, code=code, error_type="idempotency_error", details=error_details if error_details else None, cause=cause)


class IdempotencyConflictError(IdempotencyError):
    """Idempotency key conflict."""
    
    def __init__(self, key: str, message: str = "Idempotency key conflict") -> None:
        super().__init__(message=f"{message}: {key}", code="PAY_401", idempotency_key=key)
        self.key = key


class MissingIdempotencyKeyError(IdempotencyError):
    """Missing idempotency key."""
    pass


# =============================================================================
# ORDER ERRORS
# =============================================================================

class OrderError(PeoplePayError):
    """Base class for order errors."""
    
    def __init__(self, message: str = "Order error", code: str = "PAY_500", order_id: str | None = None, details: dict[str, Any] | None = None, cause: Exception | None = None) -> None:
        error_details = details or {}
        if order_id:
            error_details["order_id"] = order_id
        super().__init__(message=message, code=code, error_type="order_error", details=error_details if error_details else None, cause=cause)
        self.order_id = order_id


class OrderNotFoundError(OrderError):
    """Order not found."""
    
    def __init__(self, order_id: str) -> None:
        super().__init__(message=f"Order not found: {order_id}", code="PAY_501", order_id=order_id)


class InvalidOrderStateError(OrderError):
    """Invalid order state for operation."""
    
    def __init__(self, order_id: str, current_state: str, required_state: str | None = None) -> None:
        message = f"Order {order_id} is in state {current_state}"
        if required_state:
            message += f", requires {required_state}"
        error_details = {"current_state": current_state}
        if required_state:
            error_details["required_state"] = required_state
        super().__init__(message=message, code="PAY_502", order_id=order_id, details=error_details)
        self.current_state = current_state
        self.required_state = required_state


class OrderCannotBeModifiedError(OrderError):
    """Order cannot be modified."""
    
    def __init__(self, order_id: str, reason: str) -> None:
        super().__init__(message=f"Order {order_id} cannot be modified: {reason}", code="PAY_503", order_id=order_id, details={"reason": reason})
        self.reason = reason


# =============================================================================
# SANDBOX ERRORS
# =============================================================================

class SandboxError(PeoplePayError):
    """Base class for sandbox errors."""
    
    def __init__(self, message: str = "Sandbox error", code: str = "PAY_600", account_id: str | None = None, limit_type: str | None = None, current: int | None = None, limit: int | None = None, details: dict[str, Any] | None = None, cause: Exception | None = None) -> None:
        error_details = details or {}
        if account_id:
            error_details["account_id"] = account_id
        if limit_type:
            error_details["limit_type"] = limit_type
        if current is not None:
            error_details["current"] = current
        if limit is not None:
            error_details["limit"] = limit
        super().__init__(message=message, code=code, error_type="sandbox_error", details=error_details if error_details else None, cause=cause)


class SandboxLimitExceededError(SandboxError):
    """Sandbox limit exceeded."""
    
    def __init__(self, limit_type: str, current: int, limit: int) -> None:
        super().__init__(
            message=f"Sandbox {limit_type} limit exceeded: {current}/{limit}",
            code="PAY_601",
            limit_type=limit_type,
            current=current,
            limit=limit,
        )
        self.limit_type = limit_type
        self.current = current
        self.limit = limit


class SandboxAccountNotFoundError(SandboxError):
    """Sandbox account not found."""
    
    def __init__(self, account_id: str) -> None:
        super().__init__(message=f"Sandbox account not found: {account_id}", code="PAY_602", account_id=account_id)
        self.account_id = account_id
