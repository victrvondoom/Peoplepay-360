"""PeoplePay 360 - Payment and Commerce Service

This module provides centralized payment orchestration with:
- Orders API
- Sandbox checkout
- Payment capture and status verification
- Webhook verification
- Transaction audit trails
- Human approval before payment actions

Components:
- payment_manager.py: Main payment orchestration
- sandbox.py: Sandbox payment execution
- webhook.py: Webhook verification and processing
- audit.py: Transaction audit trails
- approval.py: Human approval workflow
- models.py: Payment data models
- errors.py: Payment-specific error handling
"""

from payment.payment_manager import (
    PaymentManager,
    get_payment_manager,
    reset_payment_manager,
)
from payment.sandbox import SandboxPaymentService
from payment.webhook import WebhookService
from payment.audit import AuditService
from payment.approval import ApprovalService
from payment.models import (
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    PaymentMethod,
    PaymentAction,
    CheckoutSession,
    CheckoutRequest,
    WebhookEvent,
    WebhookEventType,
    Currency,
    Approval,
    ApprovalStatus,
)
from payment.errors import (
    PaymentError,
    PaymentFailedError,
    PaymentNotFoundError,
    PaymentAlreadyProcessedError,
    ApprovalRequiredError,
    ApprovalDeniedError,
    IdempotencyError,
    WebhookVerificationError,
)

__all__ = [
    # Payment Manager
    "PaymentManager",
    "get_payment_manager",
    "reset_payment_manager",
    # Sandbox
    "SandboxPaymentService",
    # Webhook
    "WebhookService",
    # Audit
    "AuditService",
    # Approval
    "ApprovalService",
    # Models
    "PaymentRequest",
    "PaymentResponse",
    "PaymentStatus",
    "PaymentMethod",
    "PaymentAction",
    "CheckoutSession",
    "CheckoutRequest",
    "WebhookEvent",
    "WebhookEventType",
    "Currency",
    "Approval",
    "ApprovalStatus",
    # Errors
    "PaymentError",
    "PaymentFailedError",
    "PaymentNotFoundError",
    "PaymentAlreadyProcessedError",
    "ApprovalRequiredError",
    "ApprovalDeniedError",
    "IdempotencyError",
    "WebhookVerificationError",
]